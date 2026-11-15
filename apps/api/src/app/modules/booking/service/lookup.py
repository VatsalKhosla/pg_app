"""Bookings as other modules read them (ADR 0070): the rent agreement takes its parties, its place,
its stay and its money from here. Nothing here changes a booking, and every method runs inside the
caller's transaction. Other modules follow a booking's changes through its outbox events
(``CONFIRMED`` and ``ENDED``), never by calling into it to be told."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.ids import normalize_booking_code
from app.modules.booking.domain.state_machine import BookingStatus
from app.modules.booking.repository import BookingRepository
from app.modules.booking.service.transitions import ENDED_EARLY

if TYPE_CHECKING:
    import uuid
    from collections.abc import Collection
    from datetime import date, datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.booking.models import Booking


@dataclass(frozen=True, slots=True)
class BookingRecord:
    """A booking's facts: its parties, its PG, bed and quote, its stay, and the money it copied
    from its quote (rule 5)."""

    id: int
    public_id: uuid.UUID
    code: str
    status: BookingStatus
    student_id: int
    owner_id: int
    property_id: int
    bed_id: int
    quote_id: int
    move_in: date
    stay_months: int
    planned_move_out: date
    monthly_rent_paise: int
    token_paise: int
    due_at_move_in_paise: int
    deposit_paise: int
    monthly_charges_paise: int
    one_time_charges_paise: int
    confirmed_at: datetime | None
    # When it ended early, or when the student moved out.
    cancelled_at: datetime | None
    completed_at: datetime | None

    @property
    def was_confirmed(self) -> bool:
        """Its owner (or ops for them, or the PG itself) confirmed it at some point, whatever
        became of it since."""
        return self.confirmed_at is not None

    @property
    def ended_early(self) -> bool:
        """Rejected, cancelled, a no-show or refunded."""
        return self.status in ENDED_EARLY

    @property
    def ended(self) -> bool:
        """Over: ended early, or the stay ran its course."""
        return self.ended_early or self.status is BookingStatus.COMPLETED

    @property
    def ended_at(self) -> datetime | None:
        if self.ended_early:
            return self.cancelled_at
        return self.completed_at if self.status is BookingStatus.COMPLETED else None


def _record(booking: Booking) -> BookingRecord:
    return BookingRecord(
        id=booking.id,
        public_id=booking.public_id,
        code=booking.code,
        status=BookingStatus(booking.status),
        student_id=booking.student_id,
        owner_id=booking.owner_id,
        property_id=booking.property_id,
        bed_id=booking.bed_id,
        quote_id=booking.quote_id,
        move_in=booking.move_in,
        stay_months=booking.stay_months,
        planned_move_out=booking.planned_move_out,
        monthly_rent_paise=booking.monthly_rent_paise,
        token_paise=booking.token_paise,
        due_at_move_in_paise=booking.due_at_move_in_paise,
        deposit_paise=booking.deposit_paise,
        monthly_charges_paise=booking.monthly_charges_paise,
        one_time_charges_paise=booking.one_time_charges_paise,
        confirmed_at=booking.confirmed_at,
        cancelled_at=booking.cancelled_at,
        completed_at=booking.completed_at,
    )


class BookingLookup:
    def __init__(self, db: AsyncSession) -> None:
        self._bookings = BookingRepository(db)

    async def by_code(self, code: str) -> BookingRecord | None:
        """The booking a code someone typed names, or None."""
        canonical = normalize_booking_code(code)
        booking = None if canonical is None else await self._bookings.by_code(canonical)
        return None if booking is None else _record(booking)

    async def by_public_id(self, public_id: uuid.UUID) -> BookingRecord | None:
        booking = await self._bookings.by_public_id(public_id)
        return None if booking is None else _record(booking)

    async def by_ids(self, booking_ids: Collection[int]) -> dict[int, BookingRecord]:
        return {
            booking_id: _record(booking)
            for booking_id, booking in (await self._bookings.by_ids(booking_ids)).items()
        }
