"""Who may see a PG's owner phone, address and exact point while ``hide_owner_contact`` is on
(ADR 0026): someone with a visit booked there, or one that happened. The catalog asks through its
``ContactAccess``; this answers for visits (step 3.7), and bookings will too (Phase 5)."""

from typing import TYPE_CHECKING

from app.modules.visits.repository import VisitRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class VisitContacts:
    async def entitled(self, db: AsyncSession, *, user_id: int, property_id: int) -> bool:
        return await VisitRepository(db).entitled(user_id, property_id)
