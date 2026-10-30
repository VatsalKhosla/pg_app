"""The booking module's part of a person's data export (DPDP; ADR 0018): the bookings they made,
with the money each one fixed and every change it went through."""

from typing import TYPE_CHECKING

from app.modules.booking.repository import BookingRepository
from app.modules.catalog.service import CatalogLookup

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession


def _moment(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


async def bookings_part(db: AsyncSession, user_id: int) -> dict[str, object]:
    bookings = BookingRepository(db)
    made = await bookings.of_student(user_id)
    if not made:
        return {}
    places = await CatalogLookup(db).booking_places(
        {booking.property_id for booking in made}, verified_only=False
    )
    history = await bookings.events_of([booking.id for booking in made])
    return {
        "bookings": [
            {
                "code": booking.code,
                "pg": places[booking.property_id].name,
                "status": booking.status,
                "moveIn": booking.move_in.isoformat(),
                "stayMonths": booking.stay_months,
                "plannedMoveOut": booking.planned_move_out.isoformat(),
                "monthlyRentPaise": booking.monthly_rent_paise,
                "tokenPaise": booking.token_paise,
                "dueAtMoveInPaise": booking.due_at_move_in_paise,
                "depositPaise": booking.deposit_paise,
                "madeAt": booking.created_at.isoformat(),
                "cancelledAt": _moment(booking.cancelled_at),
                "history": [
                    {
                        "event": event.event,
                        "from": event.from_status,
                        "to": event.to_status,
                        "by": event.actor_type,
                        "at": event.created_at.isoformat(),
                    }
                    for event in history.get(booking.id, [])
                ],
            }
            for booking in made
        ]
    }
