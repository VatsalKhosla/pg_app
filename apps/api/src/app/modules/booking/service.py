"""Bookings (ARCHITECTURE §7; step 5.3 on, ADR 0046). Each method is one transaction.

A hold, as §7.3 has it, all in one transaction:

1. The Idempotency-Key is claimed, so a retry gets the first answer back.
2. The quote must be the student's own and unexpired, for a move-in still to come, at a PG the
   public may see. The booking takes the terms the quote was made under.
3. The student's holds are locked and counted against the terms' limit.
4. The room type's beds are locked, so holds on it go one at a time, and holds on them past
   their expiry are expired.
5. A free bed is chosen for the stay, in a partly held room where there is one.
6. The booking is added, HELD by the state machine, with its allocation. The exclusion
   constraint has the last word.

Every status change goes through the state machine. It is saved with a compare-and-set and
written down twice: a `booking_events` row and an audit entry.
"""

from typing import TYPE_CHECKING, Final

from sqlalchemy.exc import IntegrityError

from app.core import audit, idempotency
from app.core.calendar import india_date
from app.core.errors import InvalidTransitionError, NotFoundError
from app.core.flags import Flag
from app.core.ids import new_booking_code, normalize_booking_code
from app.modules.booking.domain.state_machine import (
    ActivateAllocation,
    BookingEvent,
    BookingFacts,
    BookingStatus,
    CancelPayment,
    DeactivateAllocation,
    Moment,
    Notify,
    Party,
    RequestPayment,
    SetCheckWindowEnd,
    SetConfirmDeadline,
    SetHoldExpiry,
    TransitionRefusedError,
    hold,
    transition,
)
from app.modules.booking.errors import BookingNeedsVisitError, HoldLimitReachedError, QuoteUsedError
from app.modules.booking.models import HOLD, Booking, BookingEventRecord, Channel
from app.modules.booking.repository import BookingRepository
from app.modules.booking.schemas import BookingPlace as PlaceSchema
from app.modules.booking.schemas import StudentBooking
from app.modules.catalog.service import CatalogLookup
from app.modules.inventory.domain.allocations import Period, stay_period
from app.modules.inventory.errors import BedUnavailableError
from app.modules.inventory.service import BedHolds
from app.modules.pricing.errors import QuoteExpiredError
from app.modules.pricing.service import BookingTerms, QuoteLookup

if TYPE_CHECKING:
    import uuid
    from collections.abc import Iterable

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.core.flags import FlagReader
    from app.modules.booking.domain.state_machine import Effect, Transition
    from app.modules.catalog.service import BookingPlace

# A random code clashing with another booking's is rare; three in a row, impossible in practice.
CODE_ATTEMPTS: Final = 3

_AUDIT_ACTORS: Final[dict[Party, audit.ActorType]] = {
    Party.STUDENT: "user",
    Party.OWNER: "owner",
    Party.OPS: "staff",
}


def _fields(effects: Iterable[Effect]) -> dict[str, object]:
    """What the effects change on the booking's own row, saved with its status."""
    fields: dict[str, object] = {}
    for effect in effects:
        match effect:
            case SetHoldExpiry(at=at):
                fields["hold_expires_at"] = at
            case SetConfirmDeadline(at=at):
                fields["confirm_by"] = at
            case SetCheckWindowEnd(at=at):
                fields["check_window_ends_at"] = at
            case _:
                pass
    return fields


class BookingService:
    def __init__(self, db: AsyncSession, clock: Clock, *, flags: FlagReader) -> None:
        self._db = db
        self._clock = clock
        self._flags = flags
        self._bookings = BookingRepository(db)
        self._catalog = CatalogLookup(db)
        self._quotes = QuoteLookup(db, clock)
        self._terms = BookingTerms(db)
        self._beds = BedHolds(db, clock)

    async def hold(
        self, actor: Actor, quote_id: uuid.UUID, *, request: idempotency.IdempotentRequest
    ) -> StudentBooking | idempotency.StoredResponse:
        """A bed of the quote's room type, held for the stay; or, for a retry of the same
        request, the answer the first one got."""
        now = self._clock.now()
        remote = await self._flags.is_enabled(Flag.REMOTE_BOOKING_ENABLED)
        verified_only = await self._flags.is_enabled(Flag.VERIFIED_ONLY)
        async with self._db.begin():
            stored = await idempotency.begin(self._db, request, clock=self._clock)
            if stored is not None:
                return stored
            if not remote:
                msg = "Beds are reserved on a visit to the PG for now. Ask to visit it."
                raise BookingNeedsVisitError(msg)
            quote = await self._quotes.usable(quote_id)
            if quote.user_id is None or quote.user_id != actor.user_id:
                raise NotFoundError
            if quote.move_in < india_date(now):
                msg = "The move-in date has passed since this price was given. Ask for a new one."
                raise QuoteExpiredError(msg)
            terms = await self._terms.of(quote.booking_policy_id)
            places = await self._catalog.booking_places(
                [quote.property_id], verified_only=verified_only
            )
            place = places[quote.property_id]
            if not place.public:
                raise NotFoundError
            await self._bookings.lock_holds_of(actor.user_id)
            allowed = terms.max_active_holds_per_user
            if await self._bookings.active_holds(actor.user_id, now=now) >= allowed:
                msg = f"You can hold {allowed} bed{'' if allowed == 1 else 's'} at a time."
                raise HoldLimitReachedError(msg)
            if await self._bookings.by_quote(quote.id) is not None:
                raise QuoteUsedError("Ask for a new price to book again.")
            rooms = await self._beds.lock_room_type(quote.room_category_id)
            beds = [bed for room in rooms for bed in room.bed_ids]
            for stale in await self._bookings.stale_holds(beds, now=now):
                await self._apply(stale, BookingEvent.HOLD_EXPIRED, Party.SYSTEM, place, by=None)
            stay = stay_period(quote.move_in, quote.stay_months)
            assert stay.end is not None  # noqa: S101 - a stay always ends
            bed = await self._beds.free_bed(rooms, stay)
            if bed is None:
                msg = "No bed of this room type is free for your stay. Try another date or room."
                raise BedUnavailableError(msg)
            step = hold(now=now, policy=terms)
            booking = Booking(
                code=new_booking_code(),
                student_id=actor.user_id,
                property_id=quote.property_id,
                room_category_id=quote.room_category_id,
                bed_id=bed,
                owner_id=place.owner_id,
                quote_id=quote.id,
                booking_policy_id=quote.booking_policy_id,
                channel=Channel.REMOTE,
                move_in=quote.move_in,
                stay_months=quote.stay_months,
                planned_move_out=stay.end,
                status=step.to,
                monthly_rent_paise=quote.monthly_rent_paise,
                fee_paise=quote.fee_paise,
                gst_paise=quote.gst_paise,
                owner_fee_total_paise=quote.owner_fee_total_paise,
                token_paise=quote.token_paise,
                due_at_move_in_paise=quote.due_at_move_in_paise,
                deposit_paise=quote.deposit_paise,
                monthly_charges_paise=quote.monthly_charges_paise,
                one_time_charges_paise=quote.one_time_charges_paise,
                **_fields(step.effects),
            )
            await self._add(booking)
            await self._carry_out(booking, step.effects, by=actor.user_id)
            await self._log(booking, HOLD, None, step, Party.STUDENT, by=actor.user_id)
            view = await self._student_view(booking, place)
            await idempotency.complete(
                self._db, request, idempotency.StoredResponse(201, view.model_dump(mode="json"))
            )
            return view

    async def mine(self, actor: Actor, code: str) -> StudentBooking:
        """The student's own booking by its code; anyone else's is a 404."""
        canonical = normalize_booking_code(code)
        if canonical is None:
            raise NotFoundError
        async with self._db.begin():
            booking = await self._bookings.by_code(canonical)
            if booking is None or booking.student_id != actor.user_id:
                raise NotFoundError
            places = await self._catalog.booking_places([booking.property_id], verified_only=False)
            return await self._student_view(booking, places[booking.property_id])

    async def _add(self, booking: Booking) -> None:
        """Adds the booking, with a new code should its random one be taken."""
        for attempt in range(1, CODE_ATTEMPTS + 1):
            try:
                async with self._db.begin_nested():
                    self._bookings.add(booking)
                    await self._db.flush()
            except IntegrityError:
                if attempt == CODE_ATTEMPTS:
                    raise
                booking.code = new_booking_code()
            else:
                break
        # The row's own defaults: its version and when it was made.
        await self._db.refresh(booking)

    async def _apply(
        self,
        booking: Booking,
        event: BookingEvent,
        party: Party,
        place: BookingPlace,
        *,
        by: int | None,
    ) -> Transition:
        """``event`` from ``party``, through the state machine: the status saved with a
        compare-and-set, the effects carried out, and the change written down."""
        terms = await self._terms.of(booking.booking_policy_id)
        facts = BookingFacts(
            status=BookingStatus(booking.status),
            move_in=booking.move_in,
            token_paise=booking.token_paise,
            instant_confirm=place.instant_confirm,
            hold_expires_at=booking.hold_expires_at,
            confirm_by=booking.confirm_by,
            check_window_ends_at=booking.check_window_ends_at,
        )
        try:
            step = transition(facts, event, party, Moment(self._clock.now()), terms)
        except TransitionRefusedError as refusal:
            raise InvalidTransitionError(refusal.reason) from refusal
        was = facts.status
        if not await self._bookings.compare_and_set(
            booking, to=step.to, values=_fields(step.effects)
        ):
            raise InvalidTransitionError("The booking changed a moment ago. Try again.")
        await self._carry_out(booking, step.effects, by=by)
        await self._log(booking, event, was, step, party, by=by)
        return step

    async def _carry_out(
        self, booking: Booking, effects: Iterable[Effect], *, by: int | None
    ) -> None:
        for effect in effects:
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
                case SetHoldExpiry() | SetConfirmDeadline() | SetCheckWindowEnd():
                    # Saved with the status.
                    pass
                case RequestPayment() | CancelPayment():
                    # The gateway's order, and withdrawing it, come with payments (Phase 6).
                    pass
                case Notify():
                    # Notifications come with the confirmation flow (5.4).
                    pass
                case _:  # pragma: no cover - each later step carries out the effects it brings
                    msg = f"{type(effect).__name__} isn't carried out yet"
                    raise NotImplementedError(msg)

    async def _log(
        self,
        booking: Booking,
        event: str,
        was: BookingStatus | None,
        step: Transition,
        party: Party,
        *,
        by: int | None,
    ) -> None:
        self._bookings.record(
            BookingEventRecord(
                booking_id=booking.id,
                event=event,
                from_status=was,
                to_status=step.to,
                actor_type=party,
                actor_id=by,
                payload={"effects": [type(effect).__name__ for effect in step.effects]},
            )
        )
        await audit.record(
            self._db,
            clock=self._clock,
            actor=audit.SYSTEM if party is Party.SYSTEM else audit.Actor(_AUDIT_ACTORS[party], by),
            action=f"booking.{event}",
            entity_type="booking",
            entity_id=booking.code,
            details={"from": was, "to": step.to},
        )

    async def _student_view(self, booking: Booking, place: BookingPlace) -> StudentBooking:
        bed = await self._catalog.bed_ref(booking.bed_id)
        return StudentBooking(
            code=booking.code,
            status=BookingStatus(booking.status),
            property=PlaceSchema(slug=place.slug, name=place.name, locality=place.locality),
            room_type=bed.category_label,
            move_in=booking.move_in,
            stay_months=booking.stay_months,
            planned_move_out=booking.planned_move_out,
            hold_expires_at=booking.hold_expires_at,
            monthly_rent_paise=booking.monthly_rent_paise,
            token_paise=booking.token_paise,
            due_at_move_in_paise=booking.due_at_move_in_paise,
            deposit_paise=booking.deposit_paise,
            monthly_charges_paise=booking.monthly_charges_paise,
            one_time_charges_paise=booking.one_time_charges_paise,
            created_at=booking.created_at,
        )
