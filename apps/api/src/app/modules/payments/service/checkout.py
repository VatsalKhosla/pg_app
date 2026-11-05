"""Paying a booking's token through checkout (ARCHITECTURE §9.2; step 6.1, ADR 0056).

The student taps Pay on their held booking, and only then is an order made, for exactly the
booking's token. Checkout hands the browser a signature, which proves who it came from and nothing
more: only the gateway's own word about the payment moves a booking, fetched here or from a verified
webhook (webhooks.py), and both come to the same settlement.

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
    PaymentMode,
    PaymentPurpose,
    Settlement,
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
from app.modules.payments.service.settlement import PaymentSettlements

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

# What the browser hears, for each thing the gateway's answer can come to besides a mismatch.
_OUTCOMES: Final = {
    Settlement.PAID: CheckoutOutcome.PAID,
    Settlement.WAITING: CheckoutOutcome.WAITING,
    Settlement.NOT_PAID: CheckoutOutcome.NOT_PAID,
    Settlement.LATE: CheckoutOutcome.LATE,
}


class TokenCheckout:
    def __init__(self, db: AsyncSession, clock: Clock, gateway: PaymentGateway) -> None:
        self._db = db
        self._clock = clock
        self._gateway = gateway
        self._payments = PaymentRepository(db)
        self._tokens = BookingTokens(db, clock)
        self._accounts = Accounts(db)
        self._settlements = PaymentSettlements(db, clock)

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

        # Of two answers at once, the second sees the first's work: the row is locked. A mismatch
        # is refused only after this commits, with its audit entry.
        async with self._db.begin():
            locked = await self._payments.by_public_id(payment_id, lock=True)
            if locked is None:  # pragma: no cover - read above, and never deleted
                raise NotFoundError
            settled = await self._settlements.apply(
                locked, found, by=audit.Actor("user", actor.user_id)
            )
        _checkouts.add(1, {"outcome": settled})
        if settled is Settlement.MISMATCH:
            raise PaymentMismatchError
        return CheckoutResult(outcome=_OUTCOMES[settled], booking=code)

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

    async def _own(self, actor: Actor, payment_id: uuid.UUID) -> Payment:
        """The student's own payment; anyone else's is a 404."""
        payment = await self._payments.by_public_id(payment_id)
        if payment is None or not await self._tokens.is_theirs(actor, payment.booking_id):
            raise NotFoundError
        return payment
