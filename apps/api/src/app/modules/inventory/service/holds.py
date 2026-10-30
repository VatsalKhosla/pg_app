"""How bookings hold beds (ARCHITECTURE §7.3; step 5.3, ADR 0046), in the booking's own
transaction.

The room type's beds are locked first, so holds on it go one at a time. A free bed is chosen for
the stay, in a partly held room where there is one, and the booking's allocation added, with the
exclusion constraint as the last word. Each change refreshes the PG's search entry, pages and
prices, as ops' blocks do.
"""

from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError

from app.core.outbox import enqueue
from app.modules.catalog.service import CatalogLookup
from app.modules.inventory.domain.allocations import AllocationKind, RoomBeds, choose_bed
from app.modules.inventory.errors import BedUnavailableError
from app.modules.inventory.models import InventoryAllocation
from app.modules.inventory.repository import AllocationRepository, to_period, to_range
from app.modules.inventory.service.allocations import ALLOCATIONS_CHANGED

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.clock import Clock
    from app.modules.inventory.domain.allocations import Period


class BedHolds:
    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._db = db
        self._clock = clock
        self._catalog = CatalogLookup(db)
        self._allocations = AllocationRepository(db)

    async def lock_room_type(self, category_id: int) -> tuple[RoomBeds, ...]:
        """The room type's beds that can be sold, room by room, locked until the transaction
        ends."""
        rooms = await self._catalog.locked_sellable_rooms(category_id)
        return tuple(RoomBeds(room.id, room.bed_ids) for room in rooms)

    async def free_bed(self, rooms: Sequence[RoomBeds], period: Period) -> int | None:
        """The bed a booking takes for ``period``, or None when every one is held on some day
        of it."""
        beds = [bed for room in rooms for bed in room.bed_ids]
        held = await self._allocations.active_overlapping(beds, period)
        return choose_bed(rooms, [(row.bed_id, to_period(row.period)) for row in held], period)

    async def hold(self, bed_id: int, period: Period, *, booking_id: int, property_id: int) -> None:
        """The booking's allocation of ``bed_id`` for ``period``. 409 BED_UNAVAILABLE if the
        exclusion constraint finds the bed held all the same."""
        row = InventoryAllocation(
            bed_id=bed_id,
            period=to_range(period),
            kind=AllocationKind.BOOKING,
            booking_id=booking_id,
        )
        self._allocations.add(row)
        try:
            async with self._db.begin_nested():
                await self._db.flush()
        except IntegrityError as error:
            msg = "The bed was taken a moment ago. Try again."
            raise BedUnavailableError(msg) from error
        await self._changed(property_id, row, "held")

    async def release(self, booking_id: int, *, property_id: int, by: int | None) -> None:
        """Frees the booking's bed: its allocation holds nothing from now on."""
        row = await self._allocations.of_booking(booking_id)
        if row is None or not row.is_active:
            return
        row.is_active = False
        row.ended_at, row.ended_by = self._clock.now(), by
        await self._changed(property_id, row, "released")

    async def _changed(self, property_id: int, row: InventoryAllocation, action: str) -> None:
        await self._db.flush()
        await enqueue(
            self._db,
            ALLOCATIONS_CHANGED,
            {"property_id": property_id},
            clock=self._clock,
            dedupe_key=f"{ALLOCATIONS_CHANGED}:{row.public_id}:{action}",
        )
