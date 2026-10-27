"""What a listing sells (ADR 0021): room categories, their rooms, and the beds in each room.

A category's money is checked by the domain and again by the database. A room takes no more
beds than its occupancy, and the room's row is locked while a bed is added, so two at once can't
both take its last place.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, NotRequired, TypedDict

from sqlalchemy.exc import IntegrityError

from app.core.errors import NotFoundError
from app.core.money import Paise
from app.modules.catalog.domain.charges import MandatoryCharge, charge_problems
from app.modules.catalog.domain.rooms import (
    BEDS_PER_ROOM,
    HIGHEST_FLOOR,
    LABEL_MAX_LENGTH,
    LOWEST_FLOOR,
    BedStatus,
    CategoryStatus,
    Occupancy,
    rent_problems,
    room_has_space,
)
from app.modules.catalog.errors import LabelTakenError, ListingInvalidError, RoomFullError
from app.modules.catalog.models import Bed, Room, RoomCategory
from app.modules.catalog.repository import CatalogRepository, charges_to_json
from app.modules.catalog.service.checks import check, text_problems
from app.modules.catalog.service.events import inventory_changed
from app.modules.catalog.service.trail import staff_did

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock

# Beds a new room gets, labelled in order.
BED_LABELS: Final = "ABCD"


@dataclass(frozen=True, slots=True)
class CategoryDraft:
    occupancy: Occupancy
    label: str
    base_rent: Paise
    security_deposit: Paise
    ac: bool = False
    attached_bath: bool = False
    balcony: bool = False
    owner_min_rent: Paise | None = None
    owner_max_rent: Paise | None = None
    mandatory_charges: tuple[MandatoryCharge, ...] = field(default=())


class CategoryChanges(TypedDict, total=False):
    """The fields to change; any left out stay as they are. Occupancy can't change: the rooms
    were made for it."""

    label: str
    ac: bool
    attached_bath: bool
    balcony: bool
    base_rent: Paise
    owner_min_rent: NotRequired[Paise | None]
    owner_max_rent: NotRequired[Paise | None]
    security_deposit: Paise
    mandatory_charges: tuple[MandatoryCharge, ...]
    status: CategoryStatus


def _label_taken(error: IntegrityError) -> bool:
    return "uq_rooms_room_category_id_label" in str(error) or "uq_beds_room_id_label" in str(error)


def _apply(category: RoomCategory, changes: CategoryChanges) -> None:
    if "label" in changes:
        category.label = changes["label"].strip()
    if "ac" in changes:
        category.ac = changes["ac"]
    if "attached_bath" in changes:
        category.attached_bath = changes["attached_bath"]
    if "balcony" in changes:
        category.balcony = changes["balcony"]
    if "base_rent" in changes:
        category.base_rent_paise = changes["base_rent"]
    if "owner_min_rent" in changes:
        category.owner_min_rent_paise = changes["owner_min_rent"]
    if "owner_max_rent" in changes:
        category.owner_max_rent_paise = changes["owner_max_rent"]
    if "security_deposit" in changes:
        category.security_deposit_paise = changes["security_deposit"]
    if "mandatory_charges" in changes:
        category.mandatory_charges = charges_to_json(changes["mandatory_charges"])
    if "status" in changes:
        category.status = changes["status"]


class InventoryService:
    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._db = db
        self._clock = clock
        self._catalog = CatalogRepository(db)

    async def add_room_category(
        self, actor: Actor, property_id: uuid.UUID, draft: CategoryDraft
    ) -> RoomCategory:
        check(
            [
                *text_problems(
                    "the label",
                    draft.label,
                    required=True,
                    max_length=LABEL_MAX_LENGTH,
                    public=True,
                ),
                *rent_problems(
                    base_rent=draft.base_rent,
                    owner_min=draft.owner_min_rent,
                    owner_max=draft.owner_max_rent,
                    deposit=draft.security_deposit,
                ),
                *charge_problems(draft.mandatory_charges),
            ]
        )
        async with self._db.begin():
            found = await self._catalog.property(property_id)
            if found is None:
                raise NotFoundError
            category = await self._catalog.add(
                RoomCategory(
                    property_id=found.id,
                    occupancy=draft.occupancy,
                    ac=draft.ac,
                    attached_bath=draft.attached_bath,
                    balcony=draft.balcony,
                    label=draft.label.strip(),
                    base_rent_paise=draft.base_rent,
                    owner_min_rent_paise=draft.owner_min_rent,
                    owner_max_rent_paise=draft.owner_max_rent,
                    security_deposit_paise=draft.security_deposit,
                    mandatory_charges=charges_to_json(draft.mandatory_charges),
                    status=CategoryStatus.ACTIVE,
                )
            )
            await staff_did(
                self._db,
                self._clock,
                actor,
                "catalog.room_category_added",
                entity="room_category",
                entity_id=category.public_id,
                property=str(found.public_id),
                base_rent_paise=draft.base_rent,
            )
            await inventory_changed(self._db, self._clock, found.id)
        return category

    async def update_room_category(
        self, actor: Actor, category_id: uuid.UUID, changes: CategoryChanges
    ) -> RoomCategory:
        problems = []
        if "label" in changes:
            problems += text_problems(
                "the label",
                changes["label"],
                required=True,
                max_length=LABEL_MAX_LENGTH,
                public=True,
            )
        if "mandatory_charges" in changes:
            problems += charge_problems(changes["mandatory_charges"])
        check(problems)
        async with self._db.begin():
            category = await self._catalog.category_for_update(category_id)
            if category is None:
                raise NotFoundError
            before = category.base_rent_paise
            _apply(category, changes)
            # The money is checked as a whole, with the fields left as they were.
            check(
                rent_problems(
                    base_rent=Paise(category.base_rent_paise),
                    owner_min=None
                    if category.owner_min_rent_paise is None
                    else Paise(category.owner_min_rent_paise),
                    owner_max=None
                    if category.owner_max_rent_paise is None
                    else Paise(category.owner_max_rent_paise),
                    deposit=Paise(category.security_deposit_paise),
                )
            )
            await self._db.flush()
            details: dict[str, object] = {"fields": sorted(changes)}
            if category.base_rent_paise != before:
                details |= {"base_rent_paise": {"from": before, "to": category.base_rent_paise}}
            await staff_did(
                self._db,
                self._clock,
                actor,
                "catalog.room_category_updated",
                entity="room_category",
                entity_id=category.public_id,
                **details,
            )
            await inventory_changed(self._db, self._clock, category.property_id)
        return category

    async def add_room(
        self,
        actor: Actor,
        category_id: uuid.UUID,
        *,
        label: str,
        floor: int | None = None,
        beds: int = 0,
    ) -> Room:
        """A room, and ``beds`` beds in it labelled A, B, ..., in one go."""
        problems = text_problems("the label", label, required=True, max_length=LABEL_MAX_LENGTH)
        if floor is not None and not LOWEST_FLOOR <= floor <= HIGHEST_FLOOR:
            problems.append(f"the floor must be from {LOWEST_FLOOR} to {HIGHEST_FLOOR}")
        check(problems)
        try:
            async with self._db.begin():
                category = await self._catalog.category(category_id)
                if category is None:
                    raise NotFoundError
                if not 0 <= beds <= BEDS_PER_ROOM[Occupancy(category.occupancy)]:
                    raise ListingInvalidError(
                        [
                            f"a {category.occupancy} room holds at most "
                            f"{BEDS_PER_ROOM[Occupancy(category.occupancy)]} beds"
                        ]
                    )
                if await self._catalog.room_label_taken(category.id, label.strip()):
                    raise LabelTakenError
                room = await self._catalog.add(
                    Room(room_category_id=category.id, label=label.strip(), floor=floor)
                )
                for bed_label in BED_LABELS[:beds]:
                    await self._catalog.add(
                        Bed(room_id=room.id, label=bed_label, status=BedStatus.ACTIVE)
                    )
                await staff_did(
                    self._db,
                    self._clock,
                    actor,
                    "catalog.room_added",
                    entity="room",
                    entity_id=room.public_id,
                    beds=beds,
                )
                await inventory_changed(self._db, self._clock, category.property_id)
        except IntegrityError as error:
            if _label_taken(error):
                raise LabelTakenError from error
            raise
        return room

    async def add_bed(self, actor: Actor, room_id: uuid.UUID, *, label: str) -> Bed:
        check(text_problems("the label", label, required=True, max_length=LABEL_MAX_LENGTH))
        try:
            async with self._db.begin():
                found = await self._catalog.room(room_id, lock=True)
                if found is None:
                    raise NotFoundError
                room, occupancy = found
                beds = await self._catalog.beds_in(room.id)
                if any(bed.label == label.strip() for bed in beds):
                    raise LabelTakenError
                if not room_has_space(occupancy, len(beds)):
                    raise RoomFullError
                bed = await self._catalog.add(
                    Bed(room_id=room.id, label=label.strip(), status=BedStatus.ACTIVE)
                )
                await staff_did(
                    self._db,
                    self._clock,
                    actor,
                    "catalog.bed_added",
                    entity="bed",
                    entity_id=bed.public_id,
                )
                property_id = (await self._catalog.property_of_room(room.id)).id
                await inventory_changed(self._db, self._clock, property_id)
        except IntegrityError as error:
            if _label_taken(error):
                raise LabelTakenError from error
            raise
        return bed

    async def set_bed_status(self, actor: Actor, bed_id: uuid.UUID, status: BedStatus) -> Bed:
        """Take a bed out of what can be sold, or put it back."""
        async with self._db.begin():
            bed = await self._catalog.bed(bed_id, lock=True)
            if bed is None:
                raise NotFoundError
            before = BedStatus(bed.status)
            bed.status = status
            await self._db.flush()
            await staff_did(
                self._db,
                self._clock,
                actor,
                "catalog.bed_status_changed",
                entity="bed",
                entity_id=bed.public_id,
                **{"from": before.value, "to": status.value},
            )
            property_id = (await self._catalog.property_of_room(bed.room_id)).id
            await inventory_changed(self._db, self._clock, property_id)
        return bed
