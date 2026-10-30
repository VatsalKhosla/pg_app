"""Queries on the allocations table. Repositories never commit; services own transactions."""

from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import Range

from app.modules.inventory.domain.allocations import Period
from app.modules.inventory.models import InventoryAllocation

if TYPE_CHECKING:
    import uuid
    from collections.abc import Collection
    from datetime import date

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.inventory.domain.allocations import AllocationKind


def to_range(period: Period) -> Range[date]:
    return Range(period.start, period.end, bounds="[)")


def to_period(held: Range[date]) -> Period:
    """A stored period as the domain reads it; the database keeps ranges as ``[start, end)``."""
    assert held.lower is not None  # noqa: S101 - the table's check refuses an open start
    return Period(held.lower, held.upper)


class AllocationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    def add(self, allocation: InventoryAllocation) -> None:
        self._db.add(allocation)

    async def get(self, public_id: uuid.UUID, *, lock: bool = False) -> InventoryAllocation | None:
        query = select(InventoryAllocation).where(InventoryAllocation.public_id == public_id)
        return await self._db.scalar(query.with_for_update() if lock else query)

    async def active_overlapping(
        self, bed_ids: Collection[int], period: Period
    ) -> list[InventoryAllocation]:
        """The active allocations of these beds that share a day with ``period``, earliest
        first."""
        if not bed_ids:
            return []
        rows = await self._db.scalars(
            select(InventoryAllocation)
            .where(
                InventoryAllocation.bed_id.in_(bed_ids),
                InventoryAllocation.is_active,
                InventoryAllocation.period.overlaps(to_range(period)),
            )
            .order_by(func.lower(InventoryAllocation.period), InventoryAllocation.id)
        )
        return list(rows)

    async def occupying(
        self, bed_ids: Collection[int], kinds: Collection[AllocationKind]
    ) -> list[InventoryAllocation]:
        """Every active allocation of ``kinds`` on these beds."""
        if not bed_ids or not kinds:
            return []
        rows = await self._db.scalars(
            select(InventoryAllocation).where(
                InventoryAllocation.bed_id.in_(bed_ids),
                InventoryAllocation.is_active,
                InventoryAllocation.kind.in_([str(kind) for kind in kinds]),
            )
        )
        return list(rows)
