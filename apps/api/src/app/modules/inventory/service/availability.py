"""Availability for other modules, inside the caller's transaction (it starts none): how many of a
PG's beds are free for a stay, and how full a room type is on a move-in (ADR 0044). Both read
the allocations through the domain's own definitions, so every module counts alike."""

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from app.modules.catalog.service import CatalogLookup
from app.modules.inventory.domain.allocations import (
    AllocationKind,
    free_beds,
    occupancy_bps,
    stay_period,
)
from app.modules.inventory.repository import AllocationRepository, to_period

if TYPE_CHECKING:
    from datetime import date

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.inventory.domain.allocations import Period

# What fills a bed for pricing's occupancy rules: tenants, never holds or maintenance. Bookings
# join from the token on, in step 5.3 (ARCHITECTURE §8.2).
OCCUPYING: Final = frozenset({AllocationKind.OFFLINE_TENANT})


class AvailabilityLookup:
    def __init__(self, db: AsyncSession) -> None:
        self._catalog = CatalogLookup(db)
        self._allocations = AllocationRepository(db)

    async def free_beds(self, property_id: int, period: Period) -> dict[int, int]:
        """Each active room type's beds that nothing holds on any day of ``period``, by the
        room type's internal id."""
        layout = await self._catalog.bed_layout(property_id)
        if layout is None:
            return {}
        categories = [category for category in layout.categories if category.active]
        owner = {bed.id: category.id for category in categories for bed in category.active_beds}
        held = await self._allocations.active_overlapping(owner.keys(), period)
        free = free_beds(
            owner.keys(), [(row.bed_id, to_period(row.period)) for row in held], period
        )
        counts = Counter(owner[bed] for bed in free)
        return {category.id: counts[category.id] for category in categories}

    async def free_beds_for_stay(
        self, property_id: int, move_in: date, stay_months: int
    ) -> dict[int, int]:
        """Each active room type's beds free for a whole stay from ``move_in``."""
        return await self.free_beds(property_id, stay_period(move_in, stay_months))


@dataclass(frozen=True, slots=True)
class CategoryOccupancy:
    """A room type's active beds and the periods tenants hold them for, read once."""

    active_beds: int
    held: tuple[Period, ...]

    def bps_on(self, day: date) -> int:
        """How full it is on ``day``, out of 10,000."""
        return occupancy_bps(self.active_beds, sum(period.holds(day) for period in self.held))


class AllocationsTaken:
    """Pricing's occupancy port (ADR 0039), from the allocations: offline tenants now, and
    bookings from the token on once they exist."""

    async def occupancy(self, db: AsyncSession, room_category_id: int) -> CategoryOccupancy:
        beds = await CatalogLookup(db).active_bed_ids(room_category_id)
        rows = await AllocationRepository(db).occupying(beds, OCCUPYING)
        return CategoryOccupancy(len(beds), tuple(to_period(row.period) for row in rows))
