"""Bodies of the inventory routes (camelCase JSON)."""

import uuid
from datetime import date
from typing import Annotated, Literal

from pydantic import StringConstraints

from app.core.schemas import ApiModel
from app.modules.inventory.domain.allocations import NOTE_MAX_LENGTH, AllocationKind


class BlockInput(ApiModel):
    """A bed held for an offline tenant or maintenance from ``start``, until ``end`` (the bed
    is free that day) or, without one, until further notice."""

    kind: Literal["offline_tenant", "maintenance"]
    start: date
    end: date | None = None
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=NOTE_MAX_LENGTH)] = ""


class BlockEnd(ApiModel):
    """The bed is free from ``on``; on or before the block's first day, it's cancelled."""

    on: date


class AllocationInfo(ApiModel):
    id: uuid.UUID
    kind: AllocationKind
    start: date
    # The day the bed is free again; null for until further notice.
    end: date | None
    note: str
    active: bool


class BlockBed(ApiModel):
    id: uuid.UUID
    label: str
    room: str


class BlockInfo(AllocationInfo):
    bed: BlockBed


class InventoryBed(ApiModel):
    id: uuid.UUID
    label: str
    room: str
    # A bed out of use isn't counted as free or sold.
    active: bool
    # What holds it in the window, earliest first.
    allocations: list[AllocationInfo]


class InventoryCategory(ApiModel):
    id: uuid.UUID
    label: str
    active: bool
    active_beds: int
    # Active beds nothing holds on any day of the window.
    free_beds: int
    beds: list[InventoryBed]


class InventoryPlace(ApiModel):
    id: uuid.UUID
    name: str


class InventoryView(ApiModel):
    """A PG's beds and what holds each from ``start`` until ``end``."""

    property: InventoryPlace
    start: date
    end: date
    categories: list[InventoryCategory]
