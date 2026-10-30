"""How full a room category is on a move-in, as the engine's occupancy rules read it (ARCHITECTURE
§8.2; ADRs 0039 and 0044).

Occupancy counts the category's beds with a booking whose token is secured, or later, and its
offline tenants; beds merely held never count, so holds can't push prices up. The inventory
module answers it from its allocations; pricing reads a category once per pass and asks it about
each move-in.
"""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import date

    from sqlalchemy.ext.asyncio import AsyncSession


class RoomOccupancy(Protocol):
    def bps_on(self, day: date) -> int:
        """The category's beds taken on ``day``, out of 10,000."""
        ...


class BedsTaken(Protocol):
    async def occupancy(self, db: AsyncSession, room_category_id: int) -> RoomOccupancy:
        """How full the category is, read once in the caller's transaction."""
        ...


class _Empty:
    def bps_on(self, day: date) -> int:
        return 0


class NoBookingsYet:
    """No bed is taken: for pricing without inventory, as tests and tools do."""

    async def occupancy(self, db: AsyncSession, room_category_id: int) -> RoomOccupancy:
        return _Empty()
