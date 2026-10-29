"""How full a room category is on a move-in, as the engine's occupancy rules read it (ARCHITECTURE
§8.2; ADR 0039).

Occupancy counts the category's beds with a booking whose token is secured, or later, and its
offline tenants; beds merely held never count, so holds can't push prices up. Bookings and their
allocations arrive in Phase 5, whose module answers this; until then no bed is taken, and the
occupancy rules wait.
"""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import date


class BedsTaken(Protocol):
    async def occupancy_bps(self, room_category_id: int, move_in: date) -> int:
        """The category's beds taken on ``move_in``, out of 10,000."""
        ...


class NoBookingsYet:
    """Before booking exists (Phase 5): no bed is taken."""

    async def occupancy_bps(self, room_category_id: int, move_in: date) -> int:
        return 0
