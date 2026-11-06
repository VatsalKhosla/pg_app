"""Tokens blocked by a UPI one-time mandate (ARCHITECTURE §9.2; step 6.7, ADR 0064).

- **Blocked:** the gateway's word that the mandate is confirmed, by webhook, by the checkout's own
  check or by reconciliation, secures the booking as a paid token would. No money has moved, so
  nothing is posted.
- **Debited:** once the booking settles (``booking.token_earned``), the debit's order goes to the
  gateway, which sends the student the notice the rules ask for, and a job debits the token after
  it. The capture posts the token as received, as a paid token's does.
- **Given back:** a booking that ends first releases the block, or, when the late-cancel rule keeps
  part of the token, debits only that part, and the bank unblocks the rest.

Each step is saved before the call that carries it out, so a job that dies is tried again and
asking twice changes nothing. Calls to the gateway happen with nothing locked.
"""

from typing import TYPE_CHECKING, Final

import structlog
from opentelemetry import metrics

from app.core import audit
from app.core.outbox import enqueue
from app.modules.booking.service import BookingTokens, TokenTaken
from app.modules.identity.service import Accounts
from app.modules.ledger.domain.ledger import token_received
from app.modules.ledger.service import Ledger
from app.modules.payments.domain.mandates import (
    PRE_DEBIT_NOTICE,
    MandatePayer,
    MandateStatus,
    kept_on_release,
)
from app.modules.payments.domain.payments import (
    INR,
    GatewayStatus,
    PaymentPurpose,
    PaymentStatus,
    Settlement,
)
from app.modules.payments.domain.reconciliation import IssueKind
from app.modules.payments.errors import PaymentGatewayRefusedError
from app.modules.payments.repository import PaymentRepository

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.clock import Clock
    from app.modules.payments.domain.mandates import GatewayMandate
    from app.modules.payments.domain.payments import GatewayPayment
    from app.modules.payments.models import Payment
    from app.modules.payments.ports import PaymentGateway

ASK: Final = "payments.mandate_ask"
ORDER_DEBIT: Final = "payments.mandate_order_debit"
DEBIT: Final = "payments.mandate_debit"
RELEASE: Final = "payments.mandate_release"

logger = structlog.stdlib.get_logger(__name__)

_mandates = metrics.get_meter("app.payments").create_counter(
    "payments.mandates", description="Tokens blocked by mandate, by what became of them"
)


def debit_receipt(payment_id: uuid.UUID) -> str:
    """The debit order's receipt: unique to the payment, 38 characters."""
    return f"debit-{payment_id.hex}"


class Mandates:
    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._db = db
        self._clock = clock
        self._payments = PaymentRepository(db)
        self._tokens = BookingTokens(db, clock)
        self._ledger = Ledger(db, clock)
        self._accounts = Accounts(db)

    # The block.

    async def note_mandate(self, payment: Payment, mandate_id: str) -> None:
        """``payment`` (locked) authorises this mandate: kept, the first time it's seen."""
        payment.provider_mandate_id = payment.provider_mandate_id or mandate_id

    async def confirmed(
        self, payment: Payment, mandate: GatewayMandate, *, by: audit.Actor
    ) -> Settlement:
        """The gateway's word on the mandate, ``payment`` locked. A confirmed one secures the
        booking, once, as a paid token would; anything else leaves it waiting."""
        if payment.status in {PaymentStatus.BLOCKED, PaymentStatus.CAPTURED}:
            return Settlement.PAID
        if payment.status == PaymentStatus.RELEASED:
            return Settlement.LATE
        if mandate.status is not MandateStatus.CONFIRMED:
            return Settlement.WAITING
        await self.note_mandate(payment, mandate.id)
        payment.status = PaymentStatus.BLOCKED
        await self._record(payment, "payment.blocked", by=by)
        _mandates.add(1, {"outcome": "blocked"})
        taken = await self._tokens.take(payment.booking_id, paid_paise=payment.amount_paise)
        if taken in {TokenTaken.SECURED, TokenTaken.REVIVED}:
            return Settlement.PAID
        if taken is TokenTaken.MOVED_ON:
            # No booking event gives this one back, so it goes from here. A hold that ended with
            # the bed gone asks for it through its own event.
            await self._release_later(payment, reason="moved_on")
        return Settlement.LATE

    async def event(self, provider: str, mandate: GatewayMandate) -> str | None:
        """A webhook about a mandate, in the job's transaction. Why it moved nothing, when someone
        should look."""
        payment = await self._payments.by_mandate(provider, mandate.id)
        if payment is None:
            # Its payment's own event, a checkout's check or reconciliation names it first.
            logger.info("a mandate event about no payment we know of yet")
            return "unknown_mandate"
        match mandate.status:
            case MandateStatus.CONFIRMED:
                await self.confirmed(payment, mandate, by=audit.SYSTEM)
            case MandateStatus.CANCELLED | MandateStatus.PAUSED:
                # Ours to cancel once we've debited or released it; anyone else's before then
                # leaves a booking whose token is no longer sure.
                if payment.status == PaymentStatus.BLOCKED and payment.debit_amount_paise is None:
                    await self._raise(
                        payment,
                        IssueKind.MANDATE_CANCELLED,
                        mandate.id,
                        "The mandate was cancelled or paused before the token was debited.",
                    )
            case MandateStatus.REJECTED | MandateStatus.INITIATED:
                pass
        return None

    async def payment_seen(self, payment: Payment, found: GatewayPayment) -> str | None:
        """A gateway's payment on one of a mandate's orders, ``payment`` locked: the
        authorisation, which names the mandate, or the debit."""
        if found.order_id is not None and found.order_id == payment.provider_debit_order_id:
            return await self.debited(payment, found)
        if found.token_id is not None and payment.provider_mandate_id is None:
            await self.note_mandate(payment, found.token_id)
            if payment.status == PaymentStatus.CREATED:
                # Webhooks come in any order: the mandate's own event may have come first and
                # found no payment to move, so the gateway is asked.
                await enqueue(
                    self._db,
                    ASK,
                    {"payment": str(payment.public_id)},
                    clock=self._clock,
                    dedupe_key=f"{ASK}:{payment.public_id}",
                )
        return None

    async def ask(self, gateway: PaymentGateway, payment_id: uuid.UUID) -> None:
        """Job: whether the mandate a payment's event named is confirmed, in the gateway's word.
        Safe to repeat."""
        payment = await self._payments.by_public_id(payment_id)
        if (
            payment is None
            or payment.status != PaymentStatus.CREATED
            or payment.provider_mandate_id is None
            or payment.provider_customer_id is None
        ):
            return
        mandate = await gateway.fetch_mandate(
            customer_id=payment.provider_customer_id, mandate_id=payment.provider_mandate_id
        )
        locked = await self._payments.by_public_id(payment_id, lock=True)
        if locked is not None:
            await self.confirmed(locked, mandate, by=audit.SYSTEM)

    # The debit.

    async def earned(self, booking: uuid.UUID) -> None:
        """A booking settled: its token, if a mandate blocked it, is debited after the notice."""
        booking_id = await self._tokens.id_of(booking)
        payment = None if booking_id is None else await self._payments.mandate_of(booking_id)
        if payment is None or payment.status != PaymentStatus.BLOCKED:
            return
        await self._debit_later(payment, payment.amount_paise)

    async def give_back(self, payment: Payment, *, refund_paise: int, reason: str) -> None:
        """A booking that ended gives its block back, ``payment`` locked: all of it, or all but
        what the late-cancel rule keeps, which is debited."""
        if payment.status != PaymentStatus.BLOCKED or payment.debit_amount_paise is not None:
            # Not blocked yet (a late confirmation is released as it comes), or already decided.
            return
        kept = kept_on_release(payment.amount_paise, refund_paise)
        if kept == 0:
            await self._release_later(payment, reason=reason)
        else:
            await self._debit_later(payment, kept)

    async def order_debit(self, gateway: PaymentGateway, payment_id: uuid.UUID) -> None:
        """Job: the debit's order, which sends the student their notice; then the debit's own job,
        for when the notice is over."""
        payment = await self._payments.by_public_id(payment_id)
        if (
            payment is None
            or payment.status != PaymentStatus.BLOCKED
            or payment.provider_mandate_id is None
            or payment.debit_amount_paise is None
            or payment.debit_after is None
        ):
            return
        if payment.provider_debit_order_id is None:
            order = await gateway.order_debit(
                mandate_id=payment.provider_mandate_id,
                amount_paise=payment.debit_amount_paise,
                receipt=debit_receipt(payment.public_id),
                after=payment.debit_after,
                notes={
                    "booking": await self._tokens.code_of(payment.booking_id),
                    "purpose": PaymentPurpose.TOKEN,
                },
            )
            locked = await self._payments.by_public_id(payment_id, lock=True)
            if locked is None or locked.provider_debit_order_id is not None:
                return
            locked.provider_debit_order_id = order.id
            await self._record(locked, "payment.debit_ordered", by=audit.SYSTEM)
        await enqueue(
            self._db,
            DEBIT,
            {"payment": str(payment_id)},
            clock=self._clock,
            run_at=payment.debit_after,
            dedupe_key=f"{DEBIT}:{payment_id}",
        )

    async def debit(self, gateway: PaymentGateway, payment_id: uuid.UUID) -> None:
        """Job, once the notice is over: the debit, which the gateway's webhook then settles. A
        refusal is final, and ops hear of it."""
        payment = await self._payments.by_public_id(payment_id)
        if (
            payment is None
            or payment.status != PaymentStatus.BLOCKED
            or payment.provider_debit_order_id is None
            or payment.provider_payment_id is not None
            or payment.provider_customer_id is None
            or payment.provider_mandate_id is None
            or payment.debit_amount_paise is None
        ):
            return
        student, code = await self._tokens.student_and_code(payment.booking_id)
        account = (await self._accounts.many([student]))[student]
        try:
            paid = await gateway.debit(
                order_id=payment.provider_debit_order_id,
                customer_id=payment.provider_customer_id,
                mandate_id=payment.provider_mandate_id,
                amount_paise=payment.debit_amount_paise,
                payer=MandatePayer(account.name, account.phone_e164),
                notes={"booking": code, "purpose": PaymentPurpose.TOKEN},
            )
        except PaymentGatewayRefusedError as error:
            locked = await self._payments.by_public_id(payment_id, lock=True)
            if locked is not None:
                await self._raise(
                    locked,
                    IssueKind.MANDATE_DEBIT_FAILED,
                    locked.provider_debit_order_id or str(payment_id),
                    f"The gateway refused the debit: {error}",
                )
            return
        locked = await self._payments.by_public_id(payment_id, lock=True)
        if locked is not None and locked.provider_payment_id is None:
            locked.provider_payment_id = paid
            await self._record(locked, "payment.debit_sent", by=audit.SYSTEM)

    async def debited(self, payment: Payment, found: GatewayPayment) -> str | None:
        """The gateway's word on the debit, ``payment`` locked: captured posts the token as
        received; anything else that isn't on its way is an issue."""
        if payment.status == PaymentStatus.CAPTURED:
            return None
        if (
            found.amount_paise != payment.debit_amount_paise
            or found.currency != INR
            or found.order_id != payment.provider_debit_order_id
        ):
            await self._raise(
                payment,
                IssueKind.MANDATE_DEBIT_FAILED,
                found.id,
                "The gateway's debit isn't the one asked for.",
            )
            return "mismatch"
        match found.status:
            case GatewayStatus.CAPTURED:
                payment.status = PaymentStatus.CAPTURED
                payment.provider_payment_id = found.id
                payment.captured_at = self._clock.now()
                await self._record(payment, "payment.captured", by=audit.SYSTEM)
                await self._ledger.post(
                    token_received(found.amount_paise),
                    key=f"token_received:{payment.public_id}",
                    booking_id=payment.booking_id,
                    booking_code=await self._tokens.code_of(payment.booking_id),
                    payment_id=payment.id,
                )
                _mandates.add(1, {"outcome": "debited"})
            case GatewayStatus.FAILED:
                await self._raise(
                    payment,
                    IssueKind.MANDATE_DEBIT_FAILED,
                    found.id,
                    "The debit failed at the student's bank.",
                )
            case _:
                pass
        return None

    # Giving the block back.

    async def release(self, gateway: PaymentGateway, payment_id: uuid.UUID) -> None:
        """Job: the mandate cancelled at the gateway, and the bank unblocks the money."""
        payment = await self._payments.by_public_id(payment_id)
        if (
            payment is None
            or payment.status != PaymentStatus.RELEASED
            or payment.provider_customer_id is None
            or payment.provider_mandate_id is None
        ):
            return
        await gateway.release_mandate(
            customer_id=payment.provider_customer_id, mandate_id=payment.provider_mandate_id
        )
        await self._record(payment, "payment.release_sent", by=audit.SYSTEM)

    async def _release_later(self, payment: Payment, *, reason: str) -> None:
        """Decided now, ``payment`` locked; the call follows in a job."""
        payment.status = PaymentStatus.RELEASED
        await self._record(payment, "payment.released", by=audit.SYSTEM, note=reason)
        _mandates.add(1, {"outcome": "released"})
        await enqueue(
            self._db,
            RELEASE,
            {"payment": str(payment.public_id)},
            clock=self._clock,
            dedupe_key=f"{RELEASE}:{payment.public_id}",
        )

    async def _debit_later(self, payment: Payment, amount_paise: int) -> None:
        """Decided now, ``payment`` locked, once: the amount, and not before the notice is over."""
        if payment.debit_amount_paise is not None:
            return
        payment.debit_amount_paise = amount_paise
        payment.debit_after = self._clock.now() + PRE_DEBIT_NOTICE
        await self._record(payment, "payment.debit_due", by=audit.SYSTEM)
        await enqueue(
            self._db,
            ORDER_DEBIT,
            {"payment": str(payment.public_id)},
            clock=self._clock,
            dedupe_key=f"{ORDER_DEBIT}:{payment.public_id}",
        )

    async def _raise(self, payment: Payment, kind: IssueKind, reference: str, detail: str) -> None:
        code = await self._tokens.code_of(payment.booking_id)
        if await self._payments.add_issue_once(
            kind=kind,
            provider=payment.provider,
            reference=reference,
            booking_code=code,
            amount_paise=payment.debit_amount_paise or payment.amount_paise,
            detail=detail,
            found_at=self._clock.now(),
        ):
            logger.error("a mandate needs someone to look at it", kind=kind, booking=code)

    async def _record(
        self, payment: Payment, action: str, *, by: audit.Actor, note: str | None = None
    ) -> None:
        details: dict[str, object] = {
            "amountPaise": payment.debit_amount_paise or payment.amount_paise,
            "mode": payment.mode,
        }
        if note is not None:
            details["note"] = note
        await audit.record(
            self._db,
            clock=self._clock,
            actor=by,
            action=action,
            entity_type="payment",
            entity_id=str(payment.public_id),
            details=details,
        )
