"""Inventory's use cases: ops' blocks on beds, and availability for the other modules."""

from app.modules.inventory.service.allocations import (
    ALLOCATIONS_CHANGED,
    WINDOW_DAYS,
    AllocationService,
    BedWindow,
    BlockView,
    CategoryWindow,
    InventoryWindow,
)
from app.modules.inventory.service.availability import (
    AllocationsTaken,
    AvailabilityLookup,
    CategoryOccupancy,
)

__all__ = [
    "ALLOCATIONS_CHANGED",
    "WINDOW_DAYS",
    "AllocationService",
    "AllocationsTaken",
    "AvailabilityLookup",
    "BedWindow",
    "BlockView",
    "CategoryOccupancy",
    "CategoryWindow",
    "InventoryWindow",
]
