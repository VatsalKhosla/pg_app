"""What payments asks of bookings (steps 6.1 and 6.2, ADRs 0056 and 0057): which booking's token
is due and how much, and that it came in, in time or not. Payments calls bookings, never the other
way round."""

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from app.core.calendar import india_date
from app.core.errors import InvalidTransitionError, NotFoundError
from app.core.ids import normalize_booking_code
from app.modules.booking.domain.state_machine import (
    BookingEvent,
    BookingStatus,
    Moment,
    Party,
    token_due,
)
from app.modules.booking.repository import BookingRepository
from app.modules.booking.service.system import BookingSystem
from app.modules.booking.service.transitions import Transitions, facts_of
from app.modules.booking.service.views import BookingViews
from app.modules.inventory.domain.allocations import Period
from app.modules.inventory.errors import BedUnavailableError
from app.modules.inventory.service import BedHolds

if TYPE_CHECKING:
    import uuid
    from collections.abc import Collection
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.modules.booking.models import Booking


@dataclass(frozen=True, slots=True)
class TokenDue:
    booking_id: int
    code: str
    amount_paise: int
    hold_expires_at: datetime


class TokenTaken(StrEnum):
    """What a token that came in came to."""

    SECURED = "secured"
    # Its hold had ended, but the bed was still free.
    REVIVED = "revived"
    # Its hold had ended and the bed had gone: the token goes back.
    REFUNDING = "refunding"
    # The booking ended some other way while the student paid: cancelled, say.
    MOVED_ON = "moved_on"


class BookingTokens:
    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._db = db
        self._clock = clock
        self._bookings = BookingRepository(db)
        self._views = BookingViews(db)
        self._system = BookingSystem(db, clock)
        self._transitions = Transitions(db, clock)
        self._beds = BedHolds(db, clock)

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

    async def id_of(self, public_id: uuid.UUID) -> int | None:
        booking = await self._bookings.by_public_id(public_id)
        return None if booking is None else booking.id

    async def own(self, actor: Actor, code: str) -> int:
        """The student's own booking; anyone else's is a 404."""
        canonical = normalize_booking_code(code)
        booking = None if canonical is None else await self._bookings.by_code(canonical)
        if booking is None or booking.student_id != actor.user_id:
            raise NotFoundError
        return booking.id

    async def found(self, code: str) -> int:
        """The booking with this code; none is a 404."""
        canonical = normalize_booking_code(code)
        booking = None if canonical is None else await self._bookings.by_code(canonical)
        if booking is None:
            raise NotFoundError
        return booking.id

    async def codes_by_id(self, booking_ids: Collection[int]) -> dict[int, str]:
        bookings = await self._bookings.by_ids(booking_ids)
        return {booking_id: booking.code for booking_id, booking in bookings.items()}

    async def student_and_code(self, booking_id: int) -> tuple[int, str]:
        booking = await self._bookings.by_id(booking_id)
        if booking is None:  # pragma: no cover - a payment always has its booking
            raise NotFoundError
        return booking.student_id, booking.code

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

    async def take(self, booking_id: int, *, paid_paise: int) -> TokenTaken:
        """The token came in, verified. What that came to, depending on where the booking has got
        to, inside the caller's transaction."""
        booking = await self._bookings.by_id(booking_id, lock=True)
        if booking is None:  # pragma: no cover - a payment always has its booking
            raise NotFoundError
        match BookingStatus(booking.status):
            case BookingStatus.HELD:
                await self._system.secure_token(booking.public_id, paid_paise=paid_paise)
                return TokenTaken.SECURED
            case BookingStatus.EXPIRED:
                return await self._late(booking, paid_paise)
            case _:
                return TokenTaken.MOVED_ON

    async def _late(self, booking: Booking, paid_paise: int) -> TokenTaken:
        """After its hold ended (§7.4): the booking takes the bed back if it's still free and the
        move-in hasn't passed; otherwise the token goes back and the booking stays ended."""
        now = self._clock.now()
        place = await self._views.place(booking)
        stay = Period(booking.move_in, booking.planned_move_out)
        # The bed counts as gone once the move-in has passed: a booking can't start on a day that's
        # over (ADR 0057).
        if india_date(now) <= booking.move_in and await self._beds.is_free(booking.bed_id, stay):
            try:
                # The check above can lose to another booking, which the constraint then refuses.
                async with self._db.begin_nested():
                    await self._transitions.apply(
                        booking,
                        BookingEvent.LATE_PAYMENT_REVIVE,
                        Party.SYSTEM,
                        place,
                        by=None,
                        moment=Moment(now, paid_paise=paid_paise, bed_free=True),
                    )
            except BedUnavailableError:
                await self._db.refresh(booking)
            else:
                return TokenTaken.REVIVED
        await self._transitions.apply(
            booking,
            BookingEvent.LATE_PAYMENT_REFUND,
            Party.SYSTEM,
            place,
            by=None,
            moment=Moment(now, paid_paise=paid_paise, bed_free=False),
        )
        return TokenTaken.REFUNDING


async def booking_codes_of(db: AsyncSession, student_id: int) -> dict[int, str]:
    """A student's bookings' codes, by the id payments know them by."""
    made = await BookingRepository(db).of_student(student_id)
    return {booking.id: booking.code for booking in made}
