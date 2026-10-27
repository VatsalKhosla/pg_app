"""Who may see a PG owner's phone, the address and the exact point while ``hide_owner_contact``
is on (ADR 0026): someone with a visit scheduled there (step 3.7) or a booking confirmed (Phase 5).

The catalog asks through ``ContactAccess``, inside its own transaction; the modules that know
about visits and bookings will answer. Until they exist, nobody is entitled.
"""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class ContactAccess(Protocol):
    async def entitled(self, db: AsyncSession, *, user_id: int, property_id: int) -> bool: ...


class NobodyYet:
    """Visits and bookings aren't built yet, so nothing entitles anyone."""

    async def entitled(self, db: AsyncSession, *, user_id: int, property_id: int) -> bool:
        return False
