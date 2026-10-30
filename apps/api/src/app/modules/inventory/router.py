"""Inventory's routes (ARCHITECTURE §15; step 5.1, ADR 0044): ops and admins see a PG's beds
over time and place or end offline-tenant and maintenance blocks. Owners get the same in Phase 7."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.clock import ClockDep
from app.core.current_actor import CurrentActor
from app.core.db import DbSession
from app.core.errors import ForbiddenError
from app.modules.inventory.domain.allocations import AllocationKind, Period
from app.modules.inventory.errors import BlockInvalidError
from app.modules.inventory.models import InventoryAllocation
from app.modules.inventory.policies import can_manage_inventory
from app.modules.inventory.schemas import (
    AllocationInfo,
    BlockBed,
    BlockEnd,
    BlockInfo,
    BlockInput,
    InventoryBed,
    InventoryCategory,
    InventoryPlace,
    InventoryView,
)
from app.modules.inventory.service import WINDOW_DAYS, AllocationService, BlockView

router = APIRouter(prefix="/v1/ops", tags=["inventory"])

# The furthest an ops view looks ahead at once.
MAX_WINDOW_DAYS = 366


def _ops(actor: CurrentActor) -> None:
    if not can_manage_inventory(actor):
        raise ForbiddenError


def _allocation(row: InventoryAllocation, period: Period) -> AllocationInfo:
    return AllocationInfo(
        id=row.public_id,
        kind=AllocationKind(row.kind),
        start=period.start,
        end=period.end,
        note=row.note,
        active=row.is_active,
    )


def _block(view: BlockView) -> BlockInfo:
    return BlockInfo(
        **_allocation(view.row, view.period).model_dump(),
        bed=BlockBed(id=view.bed.public_id, label=view.bed.label, room=view.bed.room_label),
    )


@router.get("/properties/{property_id}/inventory", summary="A PG's beds over time")
async def inventory(
    property_id: uuid.UUID,
    *,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
    start: Annotated[date | None, Query(alias="from")] = None,
    days: Annotated[int, Query(ge=1, le=MAX_WINDOW_DAYS)] = WINDOW_DAYS,
) -> InventoryView:
    """Ops and admins: every bed with what holds it from ``from`` (today unless given) for
    ``days`` days, and each room type's beds free for all of them."""
    _ops(actor)
    view = await AllocationService(db, clock).window(property_id, start=start, days=days)
    assert view.window.end is not None  # noqa: S101 - a window always has its end
    return InventoryView(
        property=InventoryPlace(id=view.layout.property_public_id, name=view.layout.name),
        start=view.window.start,
        end=view.window.end,
        categories=[
            InventoryCategory(
                id=item.category.public_id,
                label=item.category.label,
                active=item.category.active,
                active_beds=len(item.category.active_beds),
                free_beds=item.free_beds,
                beds=[
                    InventoryBed(
                        id=bed.bed.public_id,
                        label=bed.bed.label,
                        room=bed.room_label,
                        active=bed.bed.active,
                        allocations=[_allocation(row, period) for row, period in bed.allocations],
                    )
                    for bed in item.beds
                ],
            )
            for item in view.categories
        ],
    )


@router.post(
    "/beds/{bed_id}/blocks",
    status_code=status.HTTP_201_CREATED,
    summary="Hold a bed for an offline tenant or maintenance",
)
async def place_block(
    bed_id: uuid.UUID, body: BlockInput, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> BlockInfo:
    """Ops and admins. 409 BED_UNAVAILABLE, saying what holds the bed, when anything does on
    one of those days; 422 BLOCK_INVALID for a block that can't be. Audited."""
    _ops(actor)
    try:
        period = Period(body.start, body.end)
    except ValueError as error:
        raise BlockInvalidError([str(error)]) from error
    view = await AllocationService(db, clock).block(
        actor, bed_id, kind=AllocationKind(body.kind), period=period, note=body.note
    )
    return _block(view)


@router.post("/blocks/{block_id}/end", summary="End a block")
async def end_block(
    block_id: uuid.UUID, body: BlockEnd, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> BlockInfo:
    """Ops and admins: the bed is free from ``on``, sooner or later than planned; on or before
    its first day, the block is cancelled. 409 INVALID_TRANSITION for a booking's allocation or
    a cancelled block, BED_UNAVAILABLE when a later end would overlap. Audited."""
    _ops(actor)
    return _block(await AllocationService(db, clock).end(actor, block_id, on=body.on))
