"""What the system does to bookings (steps 5.4 on, ADR 0048), inside the caller's transaction:
a job's, or the payment that secures a token.

- **A secured token** moves a hold to TOKEN_SECURED. A verified gateway event will do it in
  Phase 6; until then nothing in the API does, and tests use it directly.
- **Confirmation timeouts:** an owner who doesn't answer by the booking's deadline loses it. The
  booking is rejected, its bed freed and its token refunded (§7.5, every five minutes).
- **Check windows:** once a student's 24 hours to check the room are over without a dispute, the
  booking is settled: ACTIVE, the token earned and the owner invoiced (Phase 6; §7.5, every five
  minutes).
- **Expired holds:** a hold whose time is up without the token ends, and its bed is free again
  (§7.5, every minute). A new hold on the same beds expires them itself too.
- **No-shows:** a confirmed booking whose student hasn't moved in within its terms' wait after
  the move-in ends; the bed is freed and the late-cancel rule decides the token (§7.5, daily).

Every run takes on a batch, the earliest due first, and leaves the rest to the next; each
booking moves through the state machine, so running a job twice changes nothing the second time
(step 5.8, ADR 0052).
"""

from typing import TYPE_CHECKING, Final

from app.core.errors import NotFoundError
from app.modules.booking.domain.state_machine import BookingEvent, Moment, Party, allows
from app.modules.booking.repository import BookingRepository
from app.modules.booking.service.transitions import Transitions, facts_of
from app.modules.booking.service.views import BookingViews
from app.modules.pricing.service import BookingTerms

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.clock import Clock
    from app.modules.booking.models import Booking

# How many bookings one run of a job takes on; the next run takes the rest.
BATCH: Final = 100
# The no-show run looks at every confirmed booking past its move-in, most of which are still
# within their wait, so it takes on more at once; it runs once a day.
NO_SHOW_BATCH: Final = 1_000


class BookingSystem:
    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._clock = clock
        self._bookings = BookingRepository(db)
        self._transitions = Transitions(db, clock)
        self._views = BookingViews(db)
        self._terms = BookingTerms(db)

    async def secure_token(self, booking_id: uuid.UUID, *, paid_paise: int) -> Booking:
        """The token came in: ``paid_paise``, which must be the booking's token."""
        booking = await self._bookings.by_public_id(booking_id, lock=True)
        if booking is None:
            raise NotFoundError
        await self._transitions.apply(
            booking,
            BookingEvent.TOKEN_SECURED,
            Party.SYSTEM,
            await self._views.place(booking),
            by=None,
            moment=Moment(self._clock.now(), paid_paise=paid_paise),
        )
        return booking

    async def expire_holds(self) -> int:
        """Ends the holds whose time is up, freeing their beds: how many."""
        over = await self._bookings.holds_over(self._clock.now(), limit=BATCH)
        for booking in over:
            await self._transitions.apply(
                booking,
                BookingEvent.HOLD_EXPIRED,
                Party.SYSTEM,
                await self._views.place(booking),
                by=None,
            )
        return len(over)

    async def mark_no_shows(self) -> int:
        """Ends the confirmed bookings whose student hasn't moved in within the booking's terms
        (a number of days after the move-in, in India): how many."""
        moment = Moment(self._clock.now())
        ended = 0
        for booking in await self._bookings.not_moved_in(moment.today, limit=NO_SHOW_BATCH):
            place = await self._views.place(booking)
            terms = await self._terms.of(booking.booking_policy_id)
            if not allows(
                facts_of(booking, place), BookingEvent.NO_SHOW, Party.SYSTEM, moment, terms
            ):
                continue  # still within its wait
            await self._transitions.apply(
                booking, BookingEvent.NO_SHOW, Party.SYSTEM, place, by=None, moment=moment
            )
            ended += 1
        return ended

    async def settle_check_windows(self) -> int:
        """Settles the bookings whose 24 hours to check the room are over: how many."""
        over = await self._bookings.windows_over(self._clock.now(), limit=BATCH)
        for booking in over:
            await self._transitions.apply(
                booking,
                BookingEvent.WINDOW_ELAPSED,
                Party.SYSTEM,
                await self._views.place(booking),
                by=None,
            )
        return len(over)

    async def time_out_confirmations(self) -> int:
        """Rejects the bookings whose owners didn't confirm in time: how many."""
        overdue = await self._bookings.unconfirmed_past(self._clock.now(), limit=BATCH)
        for booking in overdue:
            await self._transitions.apply(
                booking,
                BookingEvent.CONFIRM_TIMEOUT,
                Party.SYSTEM,
                await self._views.place(booking),
                by=None,
            )
        return len(overdue)
