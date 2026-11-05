"""A booking's status changes, each as one step (ADRs 0045, 0046, 0048), inside the caller's
transaction:

1. the state machine's answer, or 409 INVALID_TRANSITION;
2. the new status saved with a compare-and-set on status and version, with what the effects
   and the new status set on the row;
3. the effects carried out;
4. the change written down twice: a `booking_events` row and an audit entry.

A PG that confirms its bookings itself gets its `confirm` straight after.
"""

from typing import TYPE_CHECKING, Final, assert_never

from opentelemetry import metrics

from app.core import audit
from app.core.calendar import india_date
from app.core.errors import InvalidTransitionError
from app.core.outbox import enqueue
from app.modules.booking.domain.cancellation import late_refund
from app.modules.booking.domain.state_machine import (
    ActivateAllocation,
    ApplyLateCancelPolicy,
    AutoConfirm,
    BookingEvent,
    BookingFacts,
    BookingStatus,
    CancelPayment,
    CloseDispute,
    DeactivateAllocation,
    EarnToken,
    FlagOwner,
    IssueOwnerInvoice,
    Moment,
    Notify,
    OpenDispute,
    Party,
    RecordTokenReceived,
    RefundToken,
    RequestPayment,
    SetCheckWindowEnd,
    SetConfirmDeadline,
    SetHoldExpiry,
    SuggestSimilar,
    TransitionRefusedError,
    TruncateAllocation,
    transition,
)
from app.modules.booking.models import BookingEventRecord
from app.modules.booking.repository import BookingRepository
from app.modules.inventory.domain.allocations import Period
from app.modules.inventory.service import BedHolds
from app.modules.pricing.service import BookingTerms

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.clock import Clock
    from app.modules.booking.domain.state_machine import Effect, Transition
    from app.modules.booking.models import Booking
    from app.modules.catalog.service import BookingPlace

# A text about a booking, to the party a transition names (step 5.4, ADR 0048).
NOTIFY: Final = "booking.notify"
# Money goes back: the payments module takes it from here, since bookings never call payments.
REFUND_DUE: Final = "booking.refund_due"
# Rejected, cancelled, a no-show or refunded: the booking ended early, and the row says how.
ENDED_EARLY: Final = frozenset(
    {
        BookingStatus.REJECTED,
        BookingStatus.CANCELLED,
        BookingStatus.NO_SHOW,
        BookingStatus.REFUNDED,
    }
)
_REACHED: Final = {
    BookingStatus.TOKEN_SECURED: "token_secured_at",
    BookingStatus.CONFIRMED: "confirmed_at",
    BookingStatus.CHECKED_IN: "checked_in_at",
    BookingStatus.ACTIVE: "activated_at",
    BookingStatus.COMPLETED: "completed_at",
}
# Bookings by the changes they go through: holds expiring, tokens in, check-ins, no-shows
# (ARCHITECTURE §19).
_changed = metrics.get_meter("app.booking").create_counter(
    "booking.transitions", unit="{transition}", description="Booking status changes"
)
_AUDIT_ACTORS: Final[dict[Party, audit.ActorType]] = {
    Party.STUDENT: "user",
    Party.OWNER: "owner",
    Party.OPS: "staff",
}


def fields(effects: Iterable[Effect]) -> dict[str, object]:
    """What the effects set on the booking's own row, saved with its status."""
    found: dict[str, object] = {}
    for effect in effects:
        match effect:
            case SetHoldExpiry(at=at):
                found["hold_expires_at"] = at
            case SetConfirmDeadline(at=at):
                found["confirm_by"] = at
            case SetCheckWindowEnd(at=at):
                found["check_window_ends_at"] = at
            case TruncateAllocation(on=on):
                found["moved_out_on"] = on
            case _:
                pass
    return found


def facts_of(booking: Booking, place: BookingPlace) -> BookingFacts:
    """What the state machine reads about a booking."""
    return BookingFacts(
        status=BookingStatus(booking.status),
        move_in=booking.move_in,
        token_paise=booking.token_paise,
        instant_confirm=place.instant_confirm,
        hold_expires_at=booking.hold_expires_at,
        confirm_by=booking.confirm_by,
        check_window_ends_at=booking.check_window_ends_at,
    )


def stamps(
    to: BookingStatus, event: BookingEvent, party: Party, now: datetime
) -> dict[str, object]:
    """When the booking reached ``to``; and, if it ended early, who ended it and how."""
    if to in _REACHED:
        return {_REACHED[to]: now}
    if to in ENDED_EARLY:
        return {"cancelled_at": now, "cancelled_by": party, "cancellation_kind": event}
    return {}


class Transitions:
    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._db = db
        self._clock = clock
        self._bookings = BookingRepository(db)
        self._terms = BookingTerms(db)
        self._beds = BedHolds(db, clock)

    async def apply(
        self,
        booking: Booking,
        event: BookingEvent,
        party: Party,
        place: BookingPlace,
        *,
        by: int | None,
        moment: Moment | None = None,
        note: str | None = None,
    ) -> Transition:
        """``event`` from ``party`` (the user ``by``, None for the system), as one step."""
        now = self._clock.now()
        was = BookingStatus(booking.status)
        step = await self._step(booking, event, party, place, moment or Moment(now))
        values = fields(step.effects) | stamps(step.to, event, party, now)
        if not await self._bookings.compare_and_set(booking, to=step.to, values=values):
            raise InvalidTransitionError("The booking changed a moment ago. Try again.")
        await self.carry_out(booking, event, step, by=by)
        await self.log(booking, event, was, step, party, by=by, note=note)
        _changed.add(1, {"event": event, "from": was, "to": step.to, "by": party})
        if AutoConfirm() in step.effects:
            await self.apply(booking, BookingEvent.CONFIRM, Party.SYSTEM, place, by=None)
        return step

    async def remind_to_check_in(self, booking: Booking, place: BookingPlace, *, by: int) -> bool:
        """Ops' nudge to a student who has moved in to say so, only while they may (409
        INVALID_TRANSITION otherwise), and one text a day at most: whether it went now. Nothing
        else changes, as the check window starts on the student's own word (ADR 0050)."""
        now = self._clock.now()
        await self._step(booking, BookingEvent.CHECK_IN, Party.STUDENT, place, Moment(now))
        sent = await self._notify(
            booking,
            BookingEvent.CHECK_IN,
            Party.STUDENT,
            BookingStatus.CONFIRMED,
            instant=False,
            dedupe_key=f"{NOTIFY}:{booking.public_id}:move_in_reminder:{india_date(now)}",
        )
        await audit.record(
            self._db,
            clock=self._clock,
            actor=audit.Actor("staff", by),
            action="booking.move_in_reminder",
            entity_type="booking",
            entity_id=booking.code,
            details={"sent": sent},
        )
        return sent

    async def carry_out(  # noqa: PLR0912 - a case for each effect
        self, booking: Booking, event: str, step: Transition, *, by: int | None
    ) -> None:
        for effect in step.effects:
            match effect:
                case ActivateAllocation():
                    await self._beds.hold(
                        booking.bed_id,
                        Period(booking.move_in, booking.planned_move_out),
                        booking_id=booking.id,
                        property_id=booking.property_id,
                    )
                case DeactivateAllocation():
                    await self._beds.release(booking.id, property_id=booking.property_id, by=by)
                case TruncateAllocation(on=on):
                    await self._beds.cut_short(
                        booking.id, on, property_id=booking.property_id, by=by
                    )
                case Notify(who=who):
                    await self._notify(
                        booking, event, who, step.to, instant=AutoConfirm() in step.effects
                    )
                case SetHoldExpiry() | SetConfirmDeadline() | SetCheckWindowEnd() | AutoConfirm():
                    # Saved with the status; a confirmation of its own follows.
                    pass
                case RefundToken():
                    await self._refund(booking, event, booking.token_paise)
                case ApplyLateCancelPolicy():
                    terms = await self._terms.of(booking.booking_policy_id)
                    amount = late_refund(booking.token_paise, terms.late_cancel_policy)
                    await self._refund(booking, event, amount)
                case RequestPayment() | CancelPayment():
                    # The order is made when the student taps Pay, and a gateway's order can't be
                    # withdrawn: a token that still comes in goes back (ADRs 0056, 0057).
                    pass
                case RecordTokenReceived() | EarnToken() | IssueOwnerInvoice():
                    # The ledger and the owner's invoice come with steps 6.4 and 6.5.
                    pass
                case SuggestSimilar():
                    # The student's booking offers a search for PGs like it, from this change
                    # (ADR 0051); their text points them there.
                    pass
                case OpenDispute() | CloseDispute():
                    # The dispute's own row, the student's words and photos or ops' answer, is
                    # written by the dispute service with the change (ADR 0051).
                    pass
                case FlagOwner():
                    # The row says so, cancelled by whom and how, and the board counts each
                    # owner's cancellations from those (ADR 0054).
                    pass
                case _:
                    assert_never(effect)

    async def _refund(self, booking: Booking, event: str, amount_paise: int) -> None:
        """Asks for the money back, in this transaction, for the payments module to send."""
        if amount_paise <= 0:
            return
        await enqueue(
            self._db,
            REFUND_DUE,
            {"booking": str(booking.public_id), "amountPaise": amount_paise, "reason": event},
            clock=self._clock,
            dedupe_key=f"{REFUND_DUE}:{booking.public_id}:{event}:{booking.version}",
        )

    async def log(
        self,
        booking: Booking,
        event: str,
        was: BookingStatus | None,
        step: Transition,
        party: Party,
        *,
        by: int | None,
        note: str | None = None,
    ) -> None:
        payload: dict[str, object] = {"effects": [type(effect).__name__ for effect in step.effects]}
        if note is not None:
            payload["note"] = note
        self._bookings.record(
            BookingEventRecord(
                booking_id=booking.id,
                event=event,
                from_status=was,
                to_status=step.to,
                actor_type=party,
                actor_id=by,
                payload=payload,
            )
        )
        await audit.record(
            self._db,
            clock=self._clock,
            actor=audit.SYSTEM if party is Party.SYSTEM else audit.Actor(_AUDIT_ACTORS[party], by),
            action=f"booking.{event}",
            entity_type="booking",
            entity_id=booking.code,
            details={"from": was, "to": step.to} | ({} if note is None else {"note": note}),
        )

    async def _step(
        self,
        booking: Booking,
        event: BookingEvent,
        party: Party,
        place: BookingPlace,
        moment: Moment,
    ) -> Transition:
        """The state machine's answer, or 409 INVALID_TRANSITION."""
        terms = await self._terms.of(booking.booking_policy_id)
        try:
            return transition(facts_of(booking, place), event, party, moment, terms)
        except TransitionRefusedError as refusal:
            raise InvalidTransitionError(refusal.reason) from refusal

    async def _notify(
        self,
        booking: Booking,
        event: str,
        who: Party,
        status: BookingStatus,
        *,
        instant: bool,
        dedupe_key: str | None = None,
    ) -> bool:
        """Queues the text; once per change unless ``dedupe_key`` says otherwise."""
        payload = {
            "booking": str(booking.public_id),
            "event": event,
            "who": who,
            "status": status,
            "instant": instant,
        }
        return await enqueue(
            self._db,
            NOTIFY,
            payload,
            clock=self._clock,
            dedupe_key=dedupe_key
            or f"{NOTIFY}:{booking.public_id}:{event}:{who}:{booking.version}",
        )
