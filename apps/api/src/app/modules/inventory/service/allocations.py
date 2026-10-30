"""Ops' blocks on beds (ARCHITECTURE §7.4; step 5.1, ADR 0044): an offline tenant the owner
placed without us, or maintenance. Each method is one transaction.

A block goes on a locked bed after a check that nothing else holds it then, with the exclusion
constraint behind both as the last word. Changing a block's end is the same check again; ending
it before it starts takes it out of use. Every change is audited, and search, the PG's pages and
its prices follow.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Final

from sqlalchemy.exc import IntegrityError

from app.core import audit
from app.core.calendar import india_date
from app.core.errors import InvalidTransitionError, NotFoundError
from app.core.outbox import enqueue
from app.modules.catalog.service import CatalogLookup
from app.modules.inventory.domain.allocations import (
    BLOCK_KINDS,
    AllocationKind,
    Period,
    block_problems,
    free_beds,
)
from app.modules.inventory.errors import BedUnavailableError, BlockInvalidError
from app.modules.inventory.models import InventoryAllocation
from app.modules.inventory.repository import AllocationRepository, to_period, to_range

if TYPE_CHECKING:
    import uuid
    from datetime import date

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.modules.catalog.service import BedLayout, BedRef, LayoutBed, LayoutCategory

# The PG's beds changed hands: search, its pages and its prices follow (ADR 0044).
ALLOCATIONS_CHANGED: Final = "inventory.allocations_changed"
# How far the ops view looks ahead unless asked.
WINDOW_DAYS: Final = 120
_KIND_WORDS: Final = {
    AllocationKind.BOOKING: "a booking",
    AllocationKind.OFFLINE_TENANT: "an offline tenant",
    AllocationKind.MAINTENANCE: "maintenance",
}


def _held(bed: BedRef, row: InventoryAllocation) -> str:
    """What holds a bed, in words: "Bed A in room 101 is held by an offline tenant from 1 Aug
    2027 until further notice"."""
    period = to_period(row.period)
    until = "until further notice" if period.end is None else f"until {_day(period.end)}"
    return (
        f"Bed {bed.label} in room {bed.room_label} is held by "
        f"{_KIND_WORDS[AllocationKind(row.kind)]} from {_day(period.start)} {until}."
    )


def _day(day: date) -> str:
    """1 Aug 2027."""
    return f"{day.day} {day:%b %Y}"


@dataclass(frozen=True, slots=True)
class BlockView:
    row: InventoryAllocation
    period: Period
    bed: BedRef


@dataclass(frozen=True, slots=True)
class BedWindow:
    bed: LayoutBed
    room_label: str
    allocations: tuple[tuple[InventoryAllocation, Period], ...]


@dataclass(frozen=True, slots=True)
class CategoryWindow:
    category: LayoutCategory
    # Active beds nothing holds on any day of the window.
    free_beds: int
    beds: tuple[BedWindow, ...]


@dataclass(frozen=True, slots=True)
class InventoryWindow:
    layout: BedLayout
    window: Period
    categories: tuple[CategoryWindow, ...]


class AllocationService:
    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._db = db
        self._clock = clock
        self._catalog = CatalogLookup(db)
        self._allocations = AllocationRepository(db)

    async def window(
        self, property_id: uuid.UUID, *, start: date | None, days: int = WINDOW_DAYS
    ) -> InventoryWindow:
        """Every bed of a PG with what holds it in ``[start, start + days)`` (today unless
        given), and each room type's beds free for all of it."""
        first = start or india_date(self._clock.now())
        window = Period(first, first + timedelta(days=days))
        async with self._db.begin():
            layout = await self._catalog.bed_layout_of(property_id)
            if layout is None:
                raise NotFoundError
            bed_ids = [
                bed.id
                for category in layout.categories
                for room in category.rooms
                for bed in room.beds
            ]
            held = await self._allocations.active_overlapping(bed_ids, window)
            by_bed: dict[int, list[tuple[InventoryAllocation, Period]]] = {}
            for row in held:
                by_bed.setdefault(row.bed_id, []).append((row, to_period(row.period)))
            categories = []
            for category in layout.categories:
                active = [bed.id for bed in category.active_beds]
                free = free_beds(
                    active,
                    [(bed, period) for bed in active for _, period in by_bed.get(bed, [])],
                    window,
                )
                categories.append(
                    CategoryWindow(
                        category=category,
                        free_beds=len(free),
                        beds=tuple(
                            BedWindow(bed, room.label, tuple(by_bed.get(bed.id, [])))
                            for room in category.rooms
                            for bed in room.beds
                        ),
                    )
                )
            return InventoryWindow(layout, window, tuple(categories))

    async def block(
        self, actor: Actor, bed_id: uuid.UUID, *, kind: AllocationKind, period: Period, note: str
    ) -> BlockView:
        """Holds a bed for an offline tenant or maintenance. 409 BED_UNAVAILABLE, saying what
        holds it, when something does on any of those days."""
        now = self._clock.now()
        async with self._db.begin():
            bed = await self._catalog.locked_bed(bed_id)
            if bed is None:
                raise NotFoundError
            if problems := block_problems(kind, period, today=india_date(now), note=note):
                raise BlockInvalidError(problems)
            if clash := await self._allocations.active_overlapping([bed.id], period):
                raise BedUnavailableError(_held(bed, clash[0]))
            row = InventoryAllocation(
                bed_id=bed.id,
                period=to_range(period),
                kind=kind,
                note=note.strip(),
                created_by=actor.user_id,
            )
            self._allocations.add(row)
            await self._write(bed)
            await self._changed(actor, "inventory.block_placed", row, bed, period)
            return BlockView(row, period, bed)

    async def end(self, actor: Actor, block_id: uuid.UUID, *, on: date) -> BlockView:
        """Ends a block on ``on`` (the bed is free that day), later or sooner than planned; on
        or before its first day, the block is cancelled and holds nothing."""
        now = self._clock.now()
        async with self._db.begin():
            row = await self._allocations.get(block_id, lock=True)
            if row is None:
                raise NotFoundError
            if AllocationKind(row.kind) not in BLOCK_KINDS:
                raise InvalidTransitionError("A booking's bed changes with the booking.")
            if not row.is_active:
                raise InvalidTransitionError("That block was cancelled already.")
            bed = await self._catalog.bed_ref(row.bed_id)
            period = to_period(row.period)
            row.ended_at, row.ended_by = now, actor.user_id
            if on <= period.start:
                row.is_active = False
                action = "inventory.block_cancelled"
            else:
                period = Period(period.start, on)
                others = [
                    other
                    for other in await self._allocations.active_overlapping([bed.id], period)
                    if other.id != row.id
                ]
                if others:
                    raise BedUnavailableError(_held(bed, others[0]))
                row.period = to_range(period)
                action = "inventory.block_ended"
            await self._write(bed)
            await self._changed(actor, action, row, bed, period)
            return BlockView(row, period, bed)

    async def _write(self, bed: BedRef) -> None:
        """Flushes the change; the constraint, should it fire, is answered as a held bed."""
        try:
            async with self._db.begin_nested():
                await self._db.flush()
        except IntegrityError as error:
            msg = f"Bed {bed.label} in room {bed.room_label} is held on one of those days."
            raise BedUnavailableError(msg) from error

    async def _changed(
        self, actor: Actor, action: str, row: InventoryAllocation, bed: BedRef, period: Period
    ) -> None:
        await audit.record(
            self._db,
            clock=self._clock,
            actor=audit.Actor("staff", actor.user_id),
            action=action,
            entity_type="inventory_allocation",
            entity_id=str(row.public_id),
            details={
                "bed": str(bed.public_id),
                "kind": row.kind,
                "start": period.start.isoformat(),
                "end": None if period.end is None else period.end.isoformat(),
                "active": row.is_active,
                "note": row.note,
            },
        )
        await enqueue(
            self._db,
            ALLOCATIONS_CHANGED,
            {"property_id": bed.property_id},
            clock=self._clock,
            dedupe_key=f"{ALLOCATIONS_CHANGED}:{row.public_id}:{action}:{period.end}",
        )
