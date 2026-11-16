"""Counts of bookings for owners' insights (step 7.6, ADR 0071) and the staff dashboard, in the
caller's transaction."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.booking.repository import BookingRepository, PlacedRow

if TYPE_CHECKING:
    from datetime import date, datetime

    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class Waiting:
    """Bookings waiting for the owner's answer, and the soonest it's due."""

    count: int
    soonest: datetime | None


async def placed_stays(db: AsyncSession, owner_id: int) -> list[PlacedRow]:
    """The owner's tenants we placed (moved in), oldest first."""
    return await BookingRepository(db).placed_for_owner(owner_id)


async def waiting_for_owner(db: AsyncSession, owner_id: int) -> Waiting:
    """Bookings with the token in, waiting for the owner to confirm or turn them down."""
    count, soonest = await BookingRepository(db).waiting_for_owner(owner_id)
    return Waiting(count, soonest)


async def bookings_made(db: AsyncSession, property_id: int, start: datetime, end: datetime) -> int:
    """Bookings whose token came in during ``[start, end)``."""
    return await BookingRepository(db).secured_between(property_id, start, end)


async def secured_by_week(db: AsyncSession, start: datetime, end: datetime) -> dict[date, int]:
    """Tokens secured everywhere in ``[start, end)``, by week, for the staff dashboard."""
    return await BookingRepository(db).secured_by_week(start, end)
