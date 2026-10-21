"""Catalog use cases (ADR 0021): staff add owners and build listings (step 2.4 puts screens on
these).

Every change happens in one transaction with its audit entry. Inputs are checked against the
domain's rules, and the database checks them again. A property's display point is made when the
property is, and made again only when its exact point moves.
"""

import secrets
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, NotRequired, TypedDict

from sqlalchemy.exc import IntegrityError

from app.core import audit
from app.core.errors import InvalidTransitionError, NotFoundError
from app.core.geometry import NCR_BOUNDS, Point
from app.core.postgis import point_wkt
from app.modules.catalog.domain.charges import MandatoryCharge, charge_problems
from app.modules.catalog.domain.listing import (
    HOUSE_RULE_MAX_LENGTH,
    HOUSE_RULES_MAX,
    NAME_MAX_LENGTH,
    GenderPolicy,
    LicenceStatus,
    LocationPrecision,
    Meals,
    PropertyStatus,
    SocietyPermission,
    VerificationStatus,
    can_move,
    numbered,
    publishing_problems,
    slugify,
)
from app.modules.catalog.domain.location import moved, random_offset
from app.modules.catalog.domain.owners import NAME_MAX_LENGTH as OWNER_NAME_MAX_LENGTH
from app.modules.catalog.domain.owners import KycStatus, OwnerStatus, normalize_gstin
from app.modules.catalog.domain.rooms import (
    HIGHEST_FLOOR,
    LABEL_MAX_LENGTH,
    LOWEST_FLOOR,
    BedStatus,
    CategoryStatus,
    Occupancy,
    rent_problems,
    room_has_space,
)
from app.modules.catalog.errors import (
    LabelTakenError,
    ListingIncompleteError,
    ListingInvalidError,
    RoomFullError,
)
from app.modules.catalog.models import Bed, Owner, Property, Room, RoomCategory
from app.modules.catalog.repository import CatalogRepository, charges_to_json
from app.modules.geo.service import GeoLookup

if TYPE_CHECKING:
    import uuid
    from collections.abc import Collection
    from random import Random

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.core.money import Paise

DESCRIPTION_MAX_LENGTH: Final = 5_000
ADDRESS_MAX_LENGTH: Final = 300
LICENCE_NUMBER_MAX_LENGTH: Final = 60
# Numbered slugs tried before giving up (x-2, x-3, ...).
SLUG_ATTEMPTS: Final = 50


@dataclass(frozen=True, slots=True)
class PropertyDraft:
    owner: uuid.UUID
    locality: str
    name: str
    address_line: str
    location: Point
    location_precision: LocationPrecision
    gender_policy: GenderPolicy
    meals: Meals
    description: str = ""
    house_rules: tuple[str, ...] = ()
    licence_status: LicenceStatus = LicenceStatus.UNKNOWN
    licence_number: str | None = None
    society_permission: SocietyPermission = SocietyPermission.NOT_APPLICABLE
    instant_confirm: bool = False


class PropertyChanges(TypedDict, total=False):
    """The fields to change; any left out stay as they are."""

    name: str
    description: str
    address_line: str
    location: Point
    location_precision: LocationPrecision
    gender_policy: GenderPolicy
    meals: Meals
    house_rules: tuple[str, ...]
    licence_status: LicenceStatus
    licence_number: NotRequired[str | None]
    society_permission: SocietyPermission
    instant_confirm: bool


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


def _text_problems(name: str, value: str, *, required: bool, max_length: int) -> list[str]:
    stripped = value.strip()
    if required and not stripped:
        return [f"{name} is required"]
    if len(stripped) > max_length:
        return [f"{name} is longer than {max_length} characters"]
    return []


def _house_rule_problems(rules: Collection[str]) -> list[str]:
    if len(rules) > HOUSE_RULES_MAX:
        return [f"at most {HOUSE_RULES_MAX} house rules"]
    if any(not rule.strip() or len(rule.strip()) > HOUSE_RULE_MAX_LENGTH for rule in rules):
        return [f"each house rule needs 1 to {HOUSE_RULE_MAX_LENGTH} characters"]
    return []


def _location_problems(point: Point) -> list[str]:
    return [] if NCR_BOUNDS.contains(point) else ["the location is outside Delhi NCR"]


def _licence_problems(number: str | None) -> list[str]:
    if number is not None and not 0 < len(number.strip()) <= LICENCE_NUMBER_MAX_LENGTH:
        return [f"the licence number needs 1 to {LICENCE_NUMBER_MAX_LENGTH} characters"]
    return []


def _change_problems(changes: PropertyChanges) -> list[str]:
    """What is wrong with the fields being changed."""
    problems = []
    if "name" in changes:
        problems += _text_problems(
            "the name", changes["name"], required=True, max_length=NAME_MAX_LENGTH
        )
    if "description" in changes:
        problems += _text_problems(
            "the description",
            changes["description"],
            required=False,
            max_length=DESCRIPTION_MAX_LENGTH,
        )
    if "address_line" in changes:
        problems += _text_problems(
            "the address", changes["address_line"], required=True, max_length=ADDRESS_MAX_LENGTH
        )
    if "house_rules" in changes:
        problems += _house_rule_problems(changes["house_rules"])
    if "location" in changes:
        problems += _location_problems(changes["location"])
    if "licence_number" in changes:
        problems += _licence_problems(changes["licence_number"])
    return problems


def _apply_text(found: Property, changes: PropertyChanges) -> None:
    if "name" in changes:
        found.name = changes["name"].strip()
    if "description" in changes:
        found.description = changes["description"].strip()
    if "address_line" in changes:
        found.address_line = changes["address_line"].strip()
    if "house_rules" in changes:
        found.house_rules = [rule.strip() for rule in changes["house_rules"]]
    if "licence_number" in changes:
        number = changes["licence_number"]
        found.licence_number = None if number is None else number.strip()


def _apply_choices(found: Property, changes: PropertyChanges) -> None:
    if "location_precision" in changes:
        found.location_precision = changes["location_precision"]
    if "gender_policy" in changes:
        found.gender_policy = changes["gender_policy"]
    if "meals" in changes:
        found.meals = changes["meals"]
    if "licence_status" in changes:
        found.licence_status = changes["licence_status"]
    if "society_permission" in changes:
        found.society_permission = changes["society_permission"]
    if "instant_confirm" in changes:
        found.instant_confirm = changes["instant_confirm"]


def _check(problems: list[str]) -> None:
    if problems:
        raise ListingInvalidError(problems)


def _staff(actor: Actor) -> audit.Actor:
    return audit.Actor("staff", actor.user_id)


def _label_taken(error: IntegrityError) -> bool:
    return "uq_rooms_room_category_id_label" in str(error) or "uq_beds_room_id_label" in str(error)


class CatalogService:
    def __init__(self, db: AsyncSession, clock: Clock, *, rng: Random | None = None) -> None:
        self._db = db
        self._clock = clock
        self._catalog = CatalogRepository(db)
        self._geo = GeoLookup(db)
        # Display offsets must be unpredictable, so they come from the operating system.
        self._rng = rng or secrets.SystemRandom()

    async def _audit(
        self, actor: Actor, action: str, entity: str, entity_id: uuid.UUID, **details: object
    ) -> None:
        await audit.record(
            self._db,
            clock=self._clock,
            actor=_staff(actor),
            action=action,
            entity_type=entity,
            entity_id=str(entity_id),
            details=details,
        )

    # Owners.

    async def add_owner(
        self,
        actor: Actor,
        *,
        user_id: int,
        legal_name: str,
        business_name: str,
        gstin: str | None = None,
    ) -> Owner:
        problems = [
            *_text_problems(
                "the legal name", legal_name, required=True, max_length=OWNER_NAME_MAX_LENGTH
            ),
            *_text_problems(
                "the business name", business_name, required=True, max_length=OWNER_NAME_MAX_LENGTH
            ),
        ]
        normalized = None if gstin is None else normalize_gstin(gstin)
        if gstin is not None and normalized is None:
            problems.append("that isn't a GSTIN")
        _check(problems)
        async with self._db.begin():
            owner = await self._catalog.add(
                Owner(
                    user_id=user_id,
                    legal_name=legal_name.strip(),
                    business_name=business_name.strip(),
                    gstin=normalized,
                    kyc_status=KycStatus.NOT_STARTED,
                    status=OwnerStatus.ACTIVE,
                )
            )
            await self._audit(actor, "catalog.owner_added", "owner", owner.public_id)
        return owner

    # Properties.

    async def create_property(self, actor: Actor, draft: PropertyDraft) -> Property:
        _check(
            [
                *_text_problems("the name", draft.name, required=True, max_length=NAME_MAX_LENGTH),
                *_text_problems(
                    "the description",
                    draft.description,
                    required=False,
                    max_length=DESCRIPTION_MAX_LENGTH,
                ),
                *_text_problems(
                    "the address", draft.address_line, required=True, max_length=ADDRESS_MAX_LENGTH
                ),
                *_house_rule_problems(draft.house_rules),
                *_location_problems(draft.location),
                *_licence_problems(draft.licence_number),
            ]
        )
        async with self._db.begin():
            owner = await self._catalog.owner(draft.owner)
            locality = await self._geo.locality(draft.locality)
            if owner is None or locality is None:
                raise NotFoundError
            if owner.status != OwnerStatus.ACTIVE:
                raise ListingInvalidError(["the owner is suspended"])
            base = slugify(draft.name, locality.name)
            taken = await self._catalog.slugs_from(base)
            slug = next(
                candidate
                for candidate in (base, *(numbered(base, n) for n in range(2, SLUG_ATTEMPTS)))
                if candidate not in taken
            )
            created = await self._catalog.add(
                Property(
                    owner_id=owner.id,
                    locality_id=locality.id,
                    slug=slug,
                    name=draft.name.strip(),
                    description=draft.description.strip(),
                    address_line=draft.address_line.strip(),
                    location=point_wkt(draft.location),
                    display_location=point_wkt(moved(draft.location, random_offset(self._rng))),
                    location_precision=draft.location_precision,
                    gender_policy=draft.gender_policy,
                    meals=draft.meals,
                    house_rules=[rule.strip() for rule in draft.house_rules],
                    verification_status=VerificationStatus.UNVERIFIED,
                    licence_status=draft.licence_status,
                    licence_number=None
                    if draft.licence_number is None
                    else draft.licence_number.strip(),
                    society_permission=draft.society_permission,
                    instant_confirm=draft.instant_confirm,
                    status=PropertyStatus.DRAFT,
                )
            )
            await self._audit(
                actor, "catalog.property_created", "property", created.public_id, slug=slug
            )
        return created

    async def update_property(
        self, actor: Actor, property_id: uuid.UUID, changes: PropertyChanges
    ) -> Property:
        _check(_change_problems(changes))
        async with self._db.begin():
            found = await self._catalog.property(property_id, lock=True)
            if found is None:
                raise NotFoundError
            changed = sorted(changes)
            _apply_text(found, changes)
            _apply_choices(found, changes)
            if "location" in changes:
                exact, _ = await self._catalog.points(found.id)
                if changes["location"] == exact:
                    changed.remove("location")
                else:
                    # A new exact point gets a new display point; an unchanged one keeps its own.
                    display = moved(changes["location"], random_offset(self._rng))
                    await self._catalog.set_points(found, changes["location"], display)
            await self._db.flush()
            await self._audit(
                actor, "catalog.property_updated", "property", found.public_id, fields=changed
            )
        return found

    async def set_amenities(
        self, actor: Actor, property_id: uuid.UUID, slugs: Collection[str]
    ) -> list[str]:
        """Replace the property's amenities; returns them, by slug."""
        async with self._db.begin():
            found = await self._catalog.property(property_id, lock=True)
            if found is None:
                raise NotFoundError
            ids = await self._catalog.amenity_ids(set(slugs))
            if unknown := sorted(set(slugs) - ids.keys()):
                raise ListingInvalidError([f"no such amenity: {', '.join(unknown)}"])
            await self._catalog.set_amenities(found.id, ids.values())
            await self._audit(
                actor, "catalog.amenities_set", "property", found.public_id, amenities=sorted(ids)
            )
        return sorted(ids)

    async def move(self, actor: Actor, property_id: uuid.UUID, target: PropertyStatus) -> Property:
        """Publish, pause, delist or relist (back to draft), as the state machine allows."""
        async with self._db.begin():
            found = await self._catalog.property(property_id, lock=True)
            if found is None:
                raise NotFoundError
            current = PropertyStatus(found.status)
            if not can_move(current, target):
                raise InvalidTransitionError(f"A {current} property can't become {target}.")
            if target is PropertyStatus.PUBLISHED:
                sellable = await self._catalog.sellable_categories(found.id)
                if problems := publishing_problems(sellable_categories=sellable):
                    raise ListingIncompleteError(problems)
                if found.published_at is None:
                    found.published_at = self._clock.now()
            found.status = target
            await self._db.flush()
            await self._audit(
                actor,
                "catalog.property_status_changed",
                "property",
                found.public_id,
                **{"from": current.value, "to": target.value},
            )
        return found

    # Room categories, rooms and beds.

    async def add_room_category(
        self, actor: Actor, property_id: uuid.UUID, draft: CategoryDraft
    ) -> RoomCategory:
        _check(
            [
                *_text_problems(
                    "the label", draft.label, required=True, max_length=LABEL_MAX_LENGTH
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
            await self._audit(
                actor,
                "catalog.room_category_added",
                "room_category",
                category.public_id,
                property=str(found.public_id),
                base_rent_paise=draft.base_rent,
            )
        return category

    async def add_room(
        self, actor: Actor, category_id: uuid.UUID, *, label: str, floor: int | None = None
    ) -> Room:
        problems = _text_problems("the label", label, required=True, max_length=LABEL_MAX_LENGTH)
        if floor is not None and not LOWEST_FLOOR <= floor <= HIGHEST_FLOOR:
            problems.append(f"the floor must be from {LOWEST_FLOOR} to {HIGHEST_FLOOR}")
        _check(problems)
        try:
            async with self._db.begin():
                category = await self._catalog.category(category_id)
                if category is None:
                    raise NotFoundError
                if await self._catalog.room_label_taken(category.id, label.strip()):
                    raise LabelTakenError
                room = await self._catalog.add(
                    Room(room_category_id=category.id, label=label.strip(), floor=floor)
                )
                await self._audit(actor, "catalog.room_added", "room", room.public_id)
        except IntegrityError as error:
            if _label_taken(error):
                raise LabelTakenError from error
            raise
        return room

    async def add_bed(self, actor: Actor, room_id: uuid.UUID, *, label: str) -> Bed:
        _check(_text_problems("the label", label, required=True, max_length=LABEL_MAX_LENGTH))
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
                await self._audit(actor, "catalog.bed_added", "bed", bed.public_id)
        except IntegrityError as error:
            if _label_taken(error):
                raise LabelTakenError from error
            raise
        return bed
