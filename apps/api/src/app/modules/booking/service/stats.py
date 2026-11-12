"""Counts of a PG's bookings for its owner's insights (step 7.6), in the caller's transaction."""

from typing import TYPE_CHECKING

from app.modules.booking.repository import BookingRepository

if TYPE_CHECKING:
    from datetime import date, datetime

    from sqlalchemy.ext.asyncio import AsyncSession


async def bookings_made(db: AsyncSession, property_id: int, start: datetime, end: datetime) -> int:
    """Bookings whose token came in during ``[start, end)``."""
    return await BookingRepository(db).secured_between(property_id, start, end)


async def secured_by_week(db: AsyncSession, start: datetime, end: datetime) -> dict[date, int]:
    """Tokens secured everywhere in ``[start, end)``, by week, for the staff dashboard."""
    return await BookingRepository(db).secured_by_week(start, end)
