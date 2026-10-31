"""What the system does to bookings (steps 5.4 on, ADR 0048), inside the caller's transaction:
a job's, or the payment that secures a token.

- **A secured token** moves a hold to TOKEN_SECURED. A verified gateway event will do it in
  Phase 6; until then nothing in the API does, and tests use it directly.
- **Confirmation timeouts:** an owner who doesn't answer by the booking's deadline loses it. The
  booking is rejected, its bed freed and its token refunded (§7.5, every five minutes).
- **Check windows:** once a student's 24 hours to check the room are over without a dispute, the
  booking is settled: ACTIVE, the token earned and the owner invoiced (Phase 6; §7.5, every five
  minutes).
"""

from typing import TYPE_CHECKING, Final

from app.core.errors import NotFoundError
from app.modules.booking.domain.state_machine import BookingEvent, Moment, Party
from app.modules.booking.repository import BookingRepository
from app.modules.booking.service.transitions import Transitions
from app.modules.booking.service.views import BookingViews

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.clock import Clock
    from app.modules.booking.models import Booking

# How many bookings one run of a job takes on; the next run takes the rest.
TIMEOUT_BATCH: Final = 100


class BookingSystem:
    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._clock = clock
        self._bookings = BookingRepository(db)
        self._transitions = Transitions(db, clock)
        self._views = BookingViews(db)

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

    async def settle_check_windows(self) -> int:
        """Settles the bookings whose 24 hours to check the room are over: how many."""
        over = await self._bookings.windows_over(self._clock.now(), limit=TIMEOUT_BATCH)
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
        overdue = await self._bookings.unconfirmed_past(self._clock.now(), limit=TIMEOUT_BATCH)
        for booking in overdue:
            await self._transitions.apply(
                booking,
                BookingEvent.CONFIRM_TIMEOUT,
                Party.SYSTEM,
                await self._views.place(booking),
                by=None,
            )
        return len(overdue)
