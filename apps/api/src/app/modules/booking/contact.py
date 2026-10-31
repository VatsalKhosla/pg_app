"""Who may see a PG's owner phone, address and exact point while ``hide_owner_contact`` is on
(rule 11; ADR 0026): someone whose booking there the owner confirmed, as long as it stands or
after it ended well. The catalog asks through its ``ContactAccess``."""

from typing import TYPE_CHECKING

from app.modules.booking.repository import BookingRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class BookingContacts:
    async def entitled(self, db: AsyncSession, *, user_id: int, property_id: int) -> bool:
        return await BookingRepository(db).confirmed_at(user_id, property_id)
