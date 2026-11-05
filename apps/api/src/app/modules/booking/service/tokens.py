"""What payments asks of bookings (step 6.1, ADR 0056): which booking's token is due and how
much, and that it came in. Payments calls bookings, never the other way round."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.errors import InvalidTransitionError, NotFoundError
from app.core.ids import normalize_booking_code
from app.modules.booking.domain.state_machine import BookingStatus, token_due
from app.modules.booking.repository import BookingRepository
from app.modules.booking.service.system import BookingSystem
from app.modules.booking.service.transitions import facts_of
from app.modules.booking.service.views import BookingViews

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock


@dataclass(frozen=True, slots=True)
class TokenDue:
    booking_id: int
    code: str
    amount_paise: int
    hold_expires_at: datetime


class BookingTokens:
    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._clock = clock
        self._bookings = BookingRepository(db)
        self._views = BookingViews(db)
        self._system = BookingSystem(db, clock)

    async def due(self, actor: Actor, code: str) -> TokenDue:
        """The token the student's own booking is waiting for, which the server alone decides.
        404 for anyone else's booking; 409 once it isn't waiting."""
        canonical = normalize_booking_code(code)
        booking = None if canonical is None else await self._bookings.by_code(canonical)
        if booking is None or booking.student_id != actor.user_id:
            raise NotFoundError
        place = await self._views.place(booking)
        now = self._clock.now()
        if not token_due(facts_of(booking, place), now) or booking.hold_expires_at is None:
            raise InvalidTransitionError("This booking isn't waiting for its token any more.")
        return TokenDue(booking.id, booking.code, booking.token_paise, booking.hold_expires_at)

    async def is_theirs(self, actor: Actor, booking_id: int) -> bool:
        booking = await self._bookings.by_id(booking_id)
        return booking is not None and booking.student_id == actor.user_id

    async def code_of(self, booking_id: int) -> str:
        booking = await self._bookings.by_id(booking_id)
        if booking is None:  # pragma: no cover - a payment always has its booking
            raise NotFoundError
        return booking.code

    async def took_token(self, booking_id: int) -> bool:
        """Whether a token ever secured this booking, whatever it has come to since."""
        booking = await self._bookings.by_id(booking_id)
        return booking is not None and booking.token_secured_at is not None

    async def secure(self, booking_id: int, *, paid_paise: int) -> bool:
        """The token came in, verified. Whether that secured the booking; False when it has moved
        on, its hold over or cancelled, which leaves the money for step 6.2 to sort out."""
        booking = await self._bookings.by_id(booking_id, lock=True)
        if booking is None:  # pragma: no cover - a payment always has its booking
            raise NotFoundError
        if booking.status != BookingStatus.HELD:
            return False
        await self._system.secure_token(booking.public_id, paid_paise=paid_paise)
        return True


async def booking_codes_of(db: AsyncSession, student_id: int) -> dict[int, str]:
    """A student's bookings' codes, by the id payments know them by."""
    made = await BookingRepository(db).of_student(student_id)
    return {booking.id: booking.code for booking in made}
