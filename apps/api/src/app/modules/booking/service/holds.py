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

from app.core import idempotency
from app.core.calendar import india_date
from app.core.errors import NotFoundError
from app.core.flags import Flag
from app.core.ids import new_booking_code, normalize_booking_code
from app.modules.booking.domain.state_machine import BookingEvent, Party, hold
from app.modules.booking.errors import BookingNeedsVisitError, HoldLimitReachedError, QuoteUsedError
from app.modules.booking.models import HOLD, Booking, Channel
from app.modules.booking.repository import BookingRepository
from app.modules.booking.service.transitions import Transitions, fields
from app.modules.booking.service.views import BookingViews
from app.modules.catalog.service import CatalogLookup
from app.modules.inventory.domain.allocations import stay_period
from app.modules.inventory.errors import BedUnavailableError
from app.modules.inventory.service import BedHolds
from app.modules.pricing.errors import QuoteExpiredError
from app.modules.pricing.service import BookingTerms, QuoteLookup

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.core.flags import FlagReader
    from app.modules.booking.schemas import StudentBooking

# A random code clashing with another booking's is rare; three in a row, impossible in practice.
CODE_ATTEMPTS: Final = 3


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
        self._transitions = Transitions(db, clock)
        self._views = BookingViews(db)

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
                await self._transitions.apply(
                    stale, BookingEvent.HOLD_EXPIRED, Party.SYSTEM, place, by=None
                )
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
                **fields(step.effects),
            )
            await self._add(booking)
            await self._transitions.carry_out(booking, HOLD, step, by=actor.user_id)
            await self._transitions.log(booking, HOLD, None, step, Party.STUDENT, by=actor.user_id)
            view = await self._views.student(booking, place)
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
            return await self._views.student(booking, await self._views.place(booking))

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
