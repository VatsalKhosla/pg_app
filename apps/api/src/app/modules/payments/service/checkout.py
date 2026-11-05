"""Paying a booking's token through checkout (ARCHITECTURE §9.2; step 6.1, ADR 0056).

The student taps Pay on their held booking, and only then is an order made, for exactly the
booking's token. Checkout hands the browser a signature, which proves who it came from and nothing
more: only the gateway's own answer about the payment, fetched by the server, moves a booking
(with a verified webhook, from step 6.2).

No call to the gateway happens inside a transaction or under a lock, so each use case is a read, a
call and a write. Everything can be asked again: the order is found again by its key and receipt,
and a payment already captured moves nothing a second time.
"""

import math
from typing import TYPE_CHECKING, Final

import structlog
from opentelemetry import metrics

from app.core import audit
from app.core.errors import InvalidTransitionError, NotFoundError
from app.modules.booking.service import BookingTokens
from app.modules.identity.service import Accounts
from app.modules.payments.adapters.fake import FakeGateway
from app.modules.payments.domain.payments import (
    INR,
    GatewayPayment,
    GatewayStatus,
    PaymentMode,
    PaymentPurpose,
    PaymentStatus,
    Reading,
    advanced,
    read_payment,
    token_key,
    token_receipt,
)
from app.modules.payments.errors import (
    PaymentGatewayUnavailableError,
    PaymentMismatchError,
    PaymentSignatureInvalidError,
)
from app.modules.payments.repository import PaymentRepository
from app.modules.payments.schemas import (
    CheckoutCallback,
    CheckoutOutcome,
    CheckoutPrefill,
    CheckoutResult,
    PaymentStart,
)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.modules.booking.service import TokenDue
    from app.modules.payments.models import Payment
    from app.modules.payments.ports import PaymentGateway

logger = structlog.stdlib.get_logger(__name__)

_meter = metrics.get_meter("app.payments")
_orders = _meter.create_counter("payments.orders", description="Orders made at a gateway")
_checkouts = _meter.create_counter(
    "payments.checkouts", description="Checkouts the server has verified, by what they came to"
)

# What the gateway's answer comes to, for each thing it can mean besides a mismatch.
_OUTCOMES: Final = {
    Reading.WAITING: CheckoutOutcome.WAITING,
    Reading.NOT_PAID: CheckoutOutcome.NOT_PAID,
}


class TokenCheckout:
    def __init__(self, db: AsyncSession, clock: Clock, gateway: PaymentGateway) -> None:
        self._db = db
        self._clock = clock
        self._gateway = gateway
        self._payments = PaymentRepository(db)
        self._tokens = BookingTokens(db, clock)
        self._accounts = Accounts(db)

    async def start(self, actor: Actor, code: str) -> PaymentStart:
        """The student's held booking, ready for checkout: its order, made if there isn't one yet.
        404 for anyone else's booking; 409 once it isn't waiting for its token."""
        async with self._db.begin():
            due = await self._tokens.due(actor, code)
            key = token_key(self._gateway.name, due.code)
            payment = await self._payments.add_once(
                booking_id=due.booking_id,
                purpose=PaymentPurpose.TOKEN,
                mode=PaymentMode.PAYMENT,
                provider=self._gateway.name,
                key=key,
                amount_paise=due.amount_paise,
            )
            public_id, order_id = payment.public_id, payment.provider_order_id
            student = (await self._accounts.many([actor.user_id]))[actor.user_id]
        if order_id is None:
            order_id = await self._make_order(actor, public_id, due)
        seconds = (due.hold_expires_at - self._clock.now()).total_seconds()
        return PaymentStart(
            id=public_id,
            provider=self._gateway.name,
            key_id=self._gateway.key_id,
            order_id=order_id,
            booking=due.code,
            amount_paise=due.amount_paise,
            currency=INR,
            expires_in_seconds=max(1, math.ceil(seconds)),
            prefill=CheckoutPrefill(name=student.name, contact=student.phone_e164),
        )

    async def _make_order(self, actor: Actor, public_id: uuid.UUID, due: TokenDue) -> str:
        """The payment's order, outside any transaction. Should two requests ask at once, both
        answer with the one saved first."""
        order = await self._gateway.create_order(
            amount_paise=due.amount_paise,
            receipt=token_receipt(due.code),
            notes={"booking": due.code, "purpose": PaymentPurpose.TOKEN},
        )
        if order.amount_paise != due.amount_paise or order.currency != INR:
            logger.error("a gateway's order isn't the token asked for", booking=due.code)
            raise PaymentGatewayUnavailableError
        async with self._db.begin():
            if await self._payments.set_order_once(public_id, order.id):
                await audit.record(
                    self._db,
                    clock=self._clock,
                    actor=audit.Actor("user", actor.user_id),
                    action="payment.order_created",
                    entity_type="payment",
                    entity_id=str(public_id),
                    details={
                        "booking": due.code,
                        "amountPaise": due.amount_paise,
                        "provider": self._gateway.name,
                    },
                )
                _orders.add(1, {"provider": self._gateway.name})
            return await self._payments.order_id_of(public_id) or order.id

    async def finish(
        self, actor: Actor, payment_id: uuid.UUID, callback: CheckoutCallback
    ) -> CheckoutResult:
        """What checkout handed the browser, checked, then the gateway asked about it. The
        booking moves only on the gateway's own word that the money is in. 400 for a signature
        the gateway didn't make; 409 for a payment that isn't this order's or its amount."""
        async with self._db.begin():
            payment = await self._own(actor, payment_id)
            code = await self._tokens.code_of(payment.booking_id)
        if payment.provider_order_id is None or not self._gateway.verify_checkout_signature(
            order_id=payment.provider_order_id,
            payment_id=callback.provider_payment_id,
            signature=callback.signature,
        ):
            logger.warning("a checkout signature was refused", booking=code)
            _checkouts.add(1, {"outcome": "bad_signature"})
            raise PaymentSignatureInvalidError

        try:
            found = await self._gateway.fetch_payment(callback.provider_payment_id)
        except PaymentGatewayUnavailableError:
            # The student has paid, by the signature; the gateway can't say so yet.
            _checkouts.add(1, {"outcome": CheckoutOutcome.WAITING})
            return CheckoutResult(outcome=CheckoutOutcome.WAITING, booking=code)

        async with self._db.begin():
            reading, outcome = await self._settle(payment_id, found, actor=actor, code=code)
        _checkouts.add(1, {"outcome": reading if outcome is None else outcome})
        if outcome is None:
            logger.error("a gateway's payment doesn't match its order", booking=code)
            raise PaymentMismatchError
        return CheckoutResult(outcome=outcome, booking=code)

    async def test_checkout(self, actor: Actor, payment_id: uuid.UUID) -> CheckoutCallback:
        """The fake gateway's bank page says yes: what its checkout hands the browser. Nothing
        else has a test bank, so this is a 404 with a real gateway."""
        if not isinstance(self._gateway, FakeGateway):
            raise NotFoundError
        async with self._db.begin():
            payment = await self._own(actor, payment_id)
            order_id = payment.provider_order_id
        if order_id is None or payment.provider != self._gateway.name:
            raise InvalidTransitionError("This payment has no order to pay.")
        proof = self._gateway.checkout(order_id)
        return CheckoutCallback(provider_payment_id=proof.payment_id, signature=proof.signature)

    async def _settle(
        self, payment_id: uuid.UUID, found: GatewayPayment, *, actor: Actor, code: str
    ) -> tuple[Reading, CheckoutOutcome | None]:
        """Our payment after the gateway's answer, in one transaction with the booking's move.
        The row is locked, so of two answers at once the second sees the first's work. None for
        a mismatch, whose audit entry has to commit before it's refused."""
        payment = await self._payments.by_public_id(payment_id, lock=True)
        if payment is None:  # pragma: no cover - read above, and never deleted
            raise NotFoundError
        reading = read_payment(
            found, order_id=payment.provider_order_id or "", amount_paise=payment.amount_paise
        )
        match reading:
            case Reading.MISMATCH:
                await self._record(actor, payment, "payment.mismatch", code)
                return reading, None
            case Reading.PAID:
                return reading, await self._paid(actor, payment, found, code)
            case Reading.WAITING | Reading.NOT_PAID:
                if found.status is GatewayStatus.AUTHORIZED:
                    payment.provider_payment_id = payment.provider_payment_id or found.id
                    payment.status = advanced(PaymentStatus(payment.status), found.status)
                return reading, _OUTCOMES[reading]

    async def _paid(
        self, actor: Actor, payment: Payment, found: GatewayPayment, code: str
    ) -> CheckoutOutcome:
        """The money is in. A payment already captured moves nothing a second time, and tells the
        student the same as the first time."""
        if payment.status == PaymentStatus.CAPTURED:
            took_it = await self._tokens.took_token(payment.booking_id)
            return CheckoutOutcome.PAID if took_it else CheckoutOutcome.LATE
        payment.status = advanced(PaymentStatus(payment.status), found.status)
        payment.provider_payment_id = found.id
        payment.captured_at = self._clock.now()
        await self._record(actor, payment, "payment.captured", code)
        secured = await self._tokens.secure(payment.booking_id, paid_paise=found.amount_paise)
        if not secured:
            # Step 6.2 takes it from here: revive the booking, or refund the money (§7.4).
            logger.warning("a token came in after its booking had moved on", booking=code)
            await self._record(actor, payment, "payment.late", code)
            return CheckoutOutcome.LATE
        return CheckoutOutcome.PAID

    async def _own(self, actor: Actor, payment_id: uuid.UUID) -> Payment:
        """The student's own payment; anyone else's is a 404."""
        payment = await self._payments.by_public_id(payment_id)
        if payment is None or not await self._tokens.is_theirs(actor, payment.booking_id):
            raise NotFoundError
        return payment

    async def _record(self, actor: Actor, payment: Payment, action: str, code: str) -> None:
        await audit.record(
            self._db,
            clock=self._clock,
            actor=audit.Actor("user", actor.user_id),
            action=action,
            entity_type="payment",
            entity_id=str(payment.public_id),
            details={"booking": code, "amountPaise": payment.amount_paise},
        )
