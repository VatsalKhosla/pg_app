"""Giving money back (ARCHITECTURE §9; step 6.3, ADR 0059).

- **Automatically:** a booking's change asks for it (the state machine's RefundToken, and the
  late-cancel rule), through a job, since bookings never call payments. A token that comes in after
  its booking has moved on goes back the same way.
- **By ops:** with a reason, and a second person's approval above the threshold.
- **At the gateway:** a refund nobody here asked for, its own or from its dashboard, is recorded
  when its webhook arrives, so what students and ops see stays true.

A refund is saved first, then a job sends it, so no call to the gateway happens inside a change and
none is lost if the process dies. The refund's receipt makes sending it twice safe.
"""

import uuid
from typing import TYPE_CHECKING, Final

import structlog
from opentelemetry import metrics

from app.config import BRAND_NAME
from app.core import audit, idempotency
from app.core.errors import InvalidTransitionError, NotFoundError
from app.core.money import format_inr
from app.core.outbox import enqueue
from app.core.pagination import split_page
from app.modules.booking.service import BookingTokens
from app.modules.identity.service import Accounts
from app.modules.ledger.domain.ledger import token_refunded
from app.modules.ledger.service import Ledger
from app.modules.payments.domain.payments import PaymentStatus
from app.modules.payments.domain.refunds import (
    GatewayRefund,
    RefundKind,
    RefundStatus,
    needs_second_person,
    refund_of_receipt,
    refund_progress,
    refund_receipt,
    refundable,
)
from app.modules.payments.errors import (
    PaymentGatewayRefusedError,
    RefundNeedsSecondPersonError,
    RefundTooMuchError,
)
from app.modules.payments.repository import PaymentRepository
from app.modules.payments.schemas import OpsPayment, OpsRefund, StudentPayment, StudentRefund
from app.modules.payments.texts import REFUND_PROCESSED

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.core.idempotency import IdempotentRequest, StoredResponse
    from app.core.pagination import PageRequest
    from app.modules.payments.domain.payments import GatewayPayment
    from app.modules.payments.models import Payment, Refund
    from app.modules.payments.ports import PaymentGateway

SEND_REFUND: Final = "payments.send_refund"
REFUND_TEXT: Final = "payments.refund_text"
# What a student never hears of: ops' refund until a second person has said yes.
_HIDDEN_FROM_STUDENTS: Final = frozenset({RefundStatus.AWAITING_APPROVAL, RefundStatus.DECLINED})

logger = structlog.stdlib.get_logger(__name__)

_changes = metrics.get_meter("app.payments").create_counter(
    "payments.refunds", description="Refunds reaching a status, by kind"
)


class Refunds:
    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._db = db
        self._clock = clock
        self._payments = PaymentRepository(db)
        self._tokens = BookingTokens(db, clock)
        self._accounts = Accounts(db)
        self._ledger = Ledger(db, clock)

    async def due(self, booking: uuid.UUID, *, amount_paise: int, reason: str) -> None:
        """A booking's change gives money back: inside the job's transaction. A booking whose token
        never came through a payment has nothing to give back."""
        booking_id = await self._tokens.id_of(booking)
        payment = None if booking_id is None else await self._payments.captured_token_of(booking_id)
        if payment is None:
            logger.info("a refund was due, with no payment taken", reason=reason)
            return
        await self.automatic(payment, amount_paise=amount_paise, reason=reason)

    async def automatic(self, payment: Payment, *, amount_paise: int, reason: str) -> None:
        """``payment`` has to be locked. Only what's left of it goes back, and each reason gives
        money back once."""
        amount = min(amount_paise, await self._left(payment))
        if amount <= 0:
            logger.info("a refund was due, with nothing left to give back", reason=reason)
            return
        refund = await self._payments.add_refund_once(
            payment_id=payment.id,
            kind=RefundKind.AUTOMATIC,
            status=RefundStatus.REQUESTED,
            amount_paise=amount,
            reason=reason,
            key=f"automatic:{payment.public_id}:{reason}",
            requested_at=self._clock.now(),
            requested_by=None,
        )
        if refund is not None:
            await self._record(refund, "refund.requested", by=audit.SYSTEM)
            await self._send_later(refund)

    async def send(self, gateway: PaymentGateway, refund_id: uuid.UUID) -> None:
        """The refund to the gateway, inside the job's transaction, with nothing locked during the
        call. What may pass raises, so the job tries again; a refusal is final."""
        refund = await self._payments.refund_by_public_id(refund_id)
        if refund is None or refund.status != RefundStatus.REQUESTED:
            return
        payment = await self._payments.by_id(refund.payment_id)
        if payment.provider != gateway.name or payment.provider_payment_id is None:
            await self._failed(refund, "The payment was taken at another gateway.")
            return
        code = await self._tokens.code_of(payment.booking_id)
        try:
            found = await gateway.refund(
                payment_id=payment.provider_payment_id,
                amount_paise=refund.amount_paise,
                receipt=refund_receipt(refund.public_id),
                notes={"booking": code, "reason": refund.kind},
            )
        except PaymentGatewayRefusedError as error:
            locked = await self._payments.refund_by_public_id(refund_id, lock=True)
            if locked is not None:
                await self._failed(locked, str(error))
            return
        locked = await self._payments.refund_by_public_id(refund_id, lock=True)
        if locked is not None:
            await self._apply(locked, found)

    async def settle(
        self, provider: str, found: GatewayRefund, payment: GatewayPayment | None
    ) -> str | None:
        """A gateway's word about a refund, inside the job's transaction. Why it moved nothing, when
        someone should look."""
        refund = await self._find(found)
        if refund is None:
            refund = await self._from_gateway(provider, found, payment)
            if refund is None:
                logger.info("a refund webhook about no payment of ours")
                return "unknown_payment"
        await self._apply(refund, found)
        return None

    async def request(
        self,
        actor: Actor,
        payment_id: uuid.UUID,
        *,
        amount_paise: int,
        reason: str,
        second_person_above: int,
        request: IdempotentRequest,
    ) -> OpsRefund | StoredResponse:
        """Ops give money back, with a reason, and above the threshold only once a second person
        agrees. 409 REFUND_TOO_MUCH past what's left; 409 INVALID_TRANSITION before any came in."""
        async with self._db.begin():
            replay = await idempotency.begin(self._db, request, clock=self._clock)
            if replay is not None:
                return replay
            payment = await self._payments.by_public_id(payment_id, lock=True)
            if payment is None:
                raise NotFoundError
            if payment.status != PaymentStatus.CAPTURED:
                raise InvalidTransitionError("Only money that came in can go back.")
            await self._check_left(payment, amount_paise)
            waits = needs_second_person(amount_paise, second_person_above)
            refund = await self._payments.add_refund_once(
                payment_id=payment.id,
                kind=RefundKind.MANUAL,
                status=RefundStatus.AWAITING_APPROVAL if waits else RefundStatus.REQUESTED,
                amount_paise=amount_paise,
                reason=reason.strip(),
                key=f"manual:{uuid.uuid4()}",
                requested_at=self._clock.now(),
                requested_by=actor.user_id,
            )
            if refund is None:  # pragma: no cover - the key was made just now
                raise InvalidTransitionError("That refund was made already.")
            await self._record(refund, "refund.requested", by=audit.Actor("staff", actor.user_id))
            if not waits:
                await self._send_later(refund)
            view = await self._ops_view(refund, code=await self._tokens.code_of(payment.booking_id))
            await idempotency.complete(
                self._db, request, idempotency.StoredResponse(201, view.model_dump(mode="json"))
            )
            return view

    async def approve(self, actor: Actor, refund_id: uuid.UUID) -> OpsRefund:
        """A second person says yes. 409 REFUND_NEEDS_SECOND_PERSON for the one who asked."""
        async with self._db.begin():
            refund = await self._waiting(refund_id)
            if refund.requested_by == actor.user_id:
                raise RefundNeedsSecondPersonError
            payment = await self._payments.by_id(refund.payment_id, lock=True)
            # What's left may have changed while it waited: leave this refund out of the sum.
            await self._check_left(payment, refund.amount_paise, leaving_out=refund.id)
            refund.status = RefundStatus.REQUESTED
            refund.approved_by = actor.user_id
            await self._record(refund, "refund.approved", by=audit.Actor("staff", actor.user_id))
            await self._send_later(refund)
            return await self._ops_view(refund, code=await self._tokens.code_of(payment.booking_id))

    async def decline(self, actor: Actor, refund_id: uuid.UUID, *, reason: str) -> OpsRefund:
        """Nothing goes back. Whoever asked may withdraw it, too."""
        async with self._db.begin():
            refund = await self._waiting(refund_id)
            refund.status = RefundStatus.DECLINED
            refund.failure = reason.strip()
            await self._record(
                refund,
                "refund.declined",
                by=audit.Actor("staff", actor.user_id),
                note=reason.strip(),
            )
            payment = await self._payments.by_id(refund.payment_id)
            return await self._ops_view(refund, code=await self._tokens.code_of(payment.booking_id))

    async def page(
        self, request: PageRequest, *, status: RefundStatus | None
    ) -> tuple[list[OpsRefund], uuid.UUID | None]:
        """Ops' queue, oldest first: of one status if asked. The same few queries, however long the
        page."""
        async with self._db.begin():
            found = await self._payments.refund_page(
                status=status, after=request.after, limit=request.limit
            )
            items, next_cursor = split_page(found, request, cursor_of=lambda row: row.public_id)
            payments = await self._payments.by_ids({row.payment_id for row in items})
            codes = await self._tokens.codes_by_id(
                {payment.booking_id for payment in payments.values()}
            )
            people = await self._names(items)
        return [
            self._as_ops(row, codes[payments[row.payment_id].booking_id], people) for row in items
        ], next_cursor

    async def for_student(self, actor: Actor, code: str) -> list[StudentPayment]:
        """What the student paid for this booking, and what's coming back. 404 for anyone else's."""
        async with self._db.begin():
            booking = await self._tokens.own(actor, code)
            payments = await self._payments.of_bookings([booking])
            refunds = await self._payments.refunds_of([payment.id for payment in payments])
        return [
            StudentPayment(
                amount_paise=payment.amount_paise,
                status=PaymentStatus(payment.status),
                captured_at=payment.captured_at,
                refunds=[
                    StudentRefund(
                        amount_paise=refund.amount_paise,
                        status=RefundStatus(refund.status),
                        reference=refund.reference,
                        requested_at=refund.requested_at,
                        processed_at=refund.processed_at,
                    )
                    for refund in refunds.get(payment.id, [])
                    if refund.status not in _HIDDEN_FROM_STUDENTS
                ],
            )
            for payment in payments
        ]

    async def for_ops(self, code: str) -> list[OpsPayment]:
        """Everything taken and given back for this booking."""
        async with self._db.begin():
            booking = await self._tokens.found(code)
            payments = await self._payments.of_bookings([booking])
            refunds = await self._payments.refunds_of([payment.id for payment in payments])
            people = await self._names([row for rows in refunds.values() for row in rows])
        return [
            OpsPayment(
                id=payment.public_id,
                purpose=payment.purpose,
                provider=payment.provider,
                provider_order_id=payment.provider_order_id,
                provider_payment_id=payment.provider_payment_id,
                amount_paise=payment.amount_paise,
                status=PaymentStatus(payment.status),
                captured_at=payment.captured_at,
                refundable_paise=0
                if payment.status != PaymentStatus.CAPTURED
                else refundable(
                    payment.amount_paise,
                    [
                        (row.amount_paise, RefundStatus(row.status))
                        for row in refunds.get(payment.id, [])
                    ],
                ),
                refunds=[self._as_ops(row, code, people) for row in refunds.get(payment.id, [])],
            )
            for payment in payments
        ]

    async def text_for(self, refund_id: uuid.UUID) -> tuple[str, str, dict[str, str]] | None:
        """The phone, the template and its blanks for a refund that's gone through."""
        refund = await self._payments.refund_by_public_id(refund_id)
        if refund is None or refund.status != RefundStatus.PROCESSED:
            return None
        payment = await self._payments.by_id(refund.payment_id)
        student, code = await self._tokens.student_and_code(payment.booking_id)
        phone = (await self._accounts.many([student]))[student].phone_e164
        return (
            phone,
            REFUND_PROCESSED,
            {"brand": BRAND_NAME, "amount": format_inr(refund.amount_paise), "code": code},
        )

    async def _find(self, found: GatewayRefund) -> Refund | None:
        by_id = await self._payments.refund_by_provider_id(found.id)
        if by_id is not None:
            return by_id
        ours = refund_of_receipt(found.receipt)
        return None if ours is None else await self._payments.refund_by_public_id(ours, lock=True)

    async def _from_gateway(
        self, provider: str, found: GatewayRefund, payment: GatewayPayment | None
    ) -> Refund | None:
        """A refund nobody here asked for: its payment's, if the payment is ours."""
        ours = await self._payments.by_provider_payment(provider, found.payment_id)
        if ours is None and payment is not None and payment.order_id is not None:
            ours = await self._payments.by_order(provider, payment.order_id)
        if ours is None:
            return None
        await self._payments.add_refund_once(
            payment_id=ours.id,
            kind=RefundKind.GATEWAY,
            # It moves on as any refund does, below, with its audit entry, text and postings.
            status=RefundStatus.PENDING,
            amount_paise=found.amount_paise,
            reason="gateway",
            key=f"gateway:{found.id}",
            requested_at=self._clock.now(),
            requested_by=None,
        )
        return await self._payments.refund_by_key(f"gateway:{found.id}")

    async def _apply(self, refund: Refund, found: GatewayRefund) -> None:
        refund.provider_refund_id = refund.provider_refund_id or found.id
        refund.reference = found.reference or refund.reference
        was = RefundStatus(refund.status)
        now = refund_progress(was, found.status)
        if now is RefundStatus.FAILED and was is not RefundStatus.FAILED:
            await self._failed(refund, "The gateway couldn't send this refund.")
            return
        refund.status = now
        if now is RefundStatus.PROCESSED and refund.processed_at is None:
            refund.processed_at = self._clock.now()
            await self._record(refund, "refund.processed", by=audit.SYSTEM)
            await self._post(refund)
            _changes.add(1, {"status": now, "kind": refund.kind})
            await enqueue(
                self._db,
                REFUND_TEXT,
                {"refund": str(refund.public_id)},
                clock=self._clock,
                dedupe_key=f"{REFUND_TEXT}:{refund.public_id}",
            )

    async def _post(self, refund: Refund) -> None:
        """Money that came in has gone back. The gateway's own refund of a payment nobody captured
        never touched the books, so it posts nothing (ADR 0060)."""
        payment = await self._payments.by_id(refund.payment_id)
        if payment.status != PaymentStatus.CAPTURED:
            return
        await self._ledger.post(
            token_refunded(refund.amount_paise),
            key=f"token_refunded:{refund.public_id}",
            booking_id=payment.booking_id,
            booking_code=await self._tokens.code_of(payment.booking_id),
            payment_id=payment.id,
            memo=refund.reason,
        )

    async def _failed(self, refund: Refund, why: str) -> None:
        logger.error("a refund failed", refund=str(refund.public_id))
        refund.status = RefundStatus.FAILED
        refund.failure = why
        await self._record(refund, "refund.failed", by=audit.SYSTEM, note=why)
        _changes.add(1, {"status": RefundStatus.FAILED, "kind": refund.kind})

    async def _waiting(self, refund_id: uuid.UUID) -> Refund:
        refund = await self._payments.refund_by_public_id(refund_id, lock=True)
        if refund is None:
            raise NotFoundError
        if refund.status != RefundStatus.AWAITING_APPROVAL:
            raise InvalidTransitionError("This refund isn't waiting for an answer.")
        return refund

    async def _left(self, payment: Payment, *, leaving_out: int | None = None) -> int:
        rows = (await self._payments.refunds_of([payment.id])).get(payment.id, [])
        return refundable(
            payment.amount_paise,
            [(row.amount_paise, RefundStatus(row.status)) for row in rows if row.id != leaving_out],
        )

    async def _check_left(
        self, payment: Payment, amount_paise: int, *, leaving_out: int | None = None
    ) -> None:
        left = await self._left(payment, leaving_out=leaving_out)
        if amount_paise > left:
            msg = f"At most {format_inr(left)} of this payment can go back."
            raise RefundTooMuchError(msg)

    async def _send_later(self, refund: Refund) -> None:
        await enqueue(
            self._db,
            SEND_REFUND,
            {"refund": str(refund.public_id)},
            clock=self._clock,
            dedupe_key=f"{SEND_REFUND}:{refund.public_id}",
        )

    async def _record(
        self, refund: Refund, action: str, *, by: audit.Actor, note: str | None = None
    ) -> None:
        details: dict[str, object] = {"amountPaise": refund.amount_paise, "kind": refund.kind}
        if note is not None:
            details["note"] = note
        await audit.record(
            self._db,
            clock=self._clock,
            actor=by,
            action=action,
            entity_type="refund",
            entity_id=str(refund.public_id),
            details=details,
        )

    async def _names(self, refunds: Sequence[Refund]) -> dict[int, str | None]:
        people: Collection[int] = {
            person
            for refund in refunds
            for person in (refund.requested_by, refund.approved_by)
            if person is not None
        }
        accounts = await self._accounts.many(people)
        return {person: account.name for person, account in accounts.items()}

    async def _ops_view(self, refund: Refund, *, code: str) -> OpsRefund:
        return self._as_ops(refund, code, await self._names([refund]))

    def _as_ops(self, refund: Refund, code: str, people: dict[int, str | None]) -> OpsRefund:
        return OpsRefund(
            id=refund.public_id,
            booking=code,
            kind=RefundKind(refund.kind),
            status=RefundStatus(refund.status),
            amount_paise=refund.amount_paise,
            reason=refund.reason,
            provider_refund_id=refund.provider_refund_id,
            reference=refund.reference,
            requested_by=None if refund.requested_by is None else people.get(refund.requested_by),
            approved_by=None if refund.approved_by is None else people.get(refund.approved_by),
            requested_at=refund.requested_at,
            processed_at=refund.processed_at,
            failure=refund.failure,
        )
