"""A booking's status changes, each as one step (ADRs 0045, 0046, 0048), inside the caller's
transaction:

1. the state machine's answer, or 409 INVALID_TRANSITION;
2. the new status saved with a compare-and-set on status and version, with what the effects
   and the new status set on the row;
3. the effects carried out;
4. the change written down twice: a `booking_events` row and an audit entry.

A PG that confirms its bookings itself gets its `confirm` straight after.
"""

from typing import TYPE_CHECKING, Final

from app.core import audit
from app.core.calendar import india_date
from app.core.errors import InvalidTransitionError
from app.core.outbox import enqueue
from app.modules.booking.domain.state_machine import (
    ActivateAllocation,
    ApplyLateCancelPolicy,
    AutoConfirm,
    BookingEvent,
    BookingFacts,
    BookingStatus,
    CancelPayment,
    DeactivateAllocation,
    EarnToken,
    IssueOwnerInvoice,
    Moment,
    Notify,
    Party,
    RecordTokenReceived,
    RefundToken,
    RequestPayment,
    SetCheckWindowEnd,
    SetConfirmDeadline,
    SetHoldExpiry,
    SuggestSimilar,
    TransitionRefusedError,
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
    BookingStatus.CONFIRMED: "confirmed_at",
    BookingStatus.CHECKED_IN: "checked_in_at",
    BookingStatus.ACTIVE: "activated_at",
    BookingStatus.COMPLETED: "completed_at",
}
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

    async def carry_out(
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
                case Notify(who=who):
                    await self._notify(
                        booking, event, who, step.to, instant=AutoConfirm() in step.effects
                    )
                case SetHoldExpiry() | SetConfirmDeadline() | SetCheckWindowEnd() | AutoConfirm():
                    # Saved with the status; a confirmation of its own follows.
                    pass
                case (
                    RequestPayment()
                    | CancelPayment()
                    | RecordTokenReceived()
                    | RefundToken()
                    | ApplyLateCancelPolicy()
                    | EarnToken()
                    | IssueOwnerInvoice()
                ):
                    # The gateway's orders and refunds, the token earned, the owner's invoice and
                    # the ledger come with payments (Phase 6); until then these are stubs, and no
                    # money moves.
                    pass
                case SuggestSimilar():
                    # The student's text says so; finding them similar PGs comes with 5.7.
                    pass
                case _:  # pragma: no cover - each later step carries out the effects it brings
                    msg = f"{type(effect).__name__} isn't carried out yet"
                    raise NotImplementedError(msg)

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
