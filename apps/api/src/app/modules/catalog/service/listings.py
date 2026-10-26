"""Listings (ADR 0021, ADR 0023): staff create and edit properties, move them between draft,
published, paused and delisted, and choose their amenities and media.

Every change happens in one transaction with its audit entry. Inputs are checked against the
domain's rules, and the database checks them again. A property's display point is made when the
property is, and made again only when its exact point moves.
"""

import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, NotRequired, TypedDict

from app.core.errors import InvalidTransitionError, NotFoundError
from app.core.flags import Flag
from app.core.postgis import point_wkt
from app.modules.catalog.domain.listing import (
    NAME_MAX_LENGTH,
    GenderPolicy,
    LicenceStatus,
    LocationPrecision,
    Meals,
    PropertyStatus,
    SocietyPermission,
    VerificationStatus,
    can_move,
    free_slug,
    publishing_problems,
    slugify,
)
from app.modules.catalog.domain.location import moved, random_offset
from app.modules.catalog.domain.owners import OwnerStatus
from app.modules.catalog.errors import ListingIncompleteError, ListingInvalidError
from app.modules.catalog.models import Property
from app.modules.catalog.repository import CatalogRepository
from app.modules.catalog.service.checks import (
    ADDRESS_MAX_LENGTH,
    DESCRIPTION_MAX_LENGTH,
    check,
    house_rule_problems,
    licence_problems,
    location_problems,
    text_problems,
)
from app.modules.catalog.service.trail import staff_did
from app.modules.geo.service import GeoLookup
from app.modules.media.domain.assets import AssetStatus, Purpose
from app.modules.media.service import MediaLookup

if TYPE_CHECKING:
    import uuid
    from collections.abc import Collection, Sequence
    from random import Random

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.core.flags import FlagReader
    from app.core.geometry import Point
    from app.modules.media.service import Buckets

# Photos and videos a listing can show.
MAX_MEDIA: Final = 40
_LISTING_MEDIA: Final = frozenset({Purpose.LISTING_PHOTO, Purpose.LISTING_VIDEO})


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


def _change_problems(changes: PropertyChanges) -> list[str]:
    """What is wrong with the fields being changed."""
    problems = []
    if "name" in changes:
        problems += text_problems(
            "the name", changes["name"], required=True, max_length=NAME_MAX_LENGTH
        )
    if "description" in changes:
        problems += text_problems(
            "the description",
            changes["description"],
            required=False,
            max_length=DESCRIPTION_MAX_LENGTH,
        )
    if "address_line" in changes:
        problems += text_problems(
            "the address", changes["address_line"], required=True, max_length=ADDRESS_MAX_LENGTH
        )
    if "house_rules" in changes:
        problems += house_rule_problems(changes["house_rules"])
    if "location" in changes:
        problems += location_problems(changes["location"])
    if "licence_number" in changes:
        problems += licence_problems(changes["licence_number"])
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


class ListingService:
    def __init__(
        self,
        db: AsyncSession,
        clock: Clock,
        *,
        buckets: Buckets,
        flags: FlagReader,
        rng: Random | None = None,
    ) -> None:
        self._db = db
        self._clock = clock
        self._flags = flags
        self._catalog = CatalogRepository(db)
        self._geo = GeoLookup(db)
        self._media = MediaLookup(db, buckets)
        # Display offsets must be unpredictable, so they come from the operating system.
        self._rng = rng or secrets.SystemRandom()

    # Properties.

    async def create_property(self, actor: Actor, draft: PropertyDraft) -> Property:
        check(
            [
                *text_problems("the name", draft.name, required=True, max_length=NAME_MAX_LENGTH),
                *text_problems(
                    "the description",
                    draft.description,
                    required=False,
                    max_length=DESCRIPTION_MAX_LENGTH,
                ),
                *text_problems(
                    "the address", draft.address_line, required=True, max_length=ADDRESS_MAX_LENGTH
                ),
                *house_rule_problems(draft.house_rules),
                *location_problems(draft.location),
                *licence_problems(draft.licence_number),
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
            slug = free_slug(base, taken)
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
            await staff_did(
                self._db,
                self._clock,
                actor,
                "catalog.property_created",
                entity="property",
                entity_id=created.public_id,
                slug=slug,
            )
        return created

    async def update_property(
        self, actor: Actor, property_id: uuid.UUID, changes: PropertyChanges
    ) -> Property:
        check(_change_problems(changes))
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
            await staff_did(
                self._db,
                self._clock,
                actor,
                "catalog.property_updated",
                entity="property",
                entity_id=found.public_id,
                fields=changed,
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
            await staff_did(
                self._db,
                self._clock,
                actor,
                "catalog.amenities_set",
                entity="property",
                entity_id=found.public_id,
                amenities=sorted(ids),
            )
        return sorted(ids)

    async def move(self, actor: Actor, property_id: uuid.UUID, target: PropertyStatus) -> Property:
        """Publish, pause, delist or relist (back to draft), as the state machine allows.
        Publishing needs something to sell and, while the flag says so, a passed verification."""
        # Read before the transaction: the flags have their own session, and no lock is held yet.
        verified_only = await self._flags.is_enabled(Flag.VERIFIED_ONLY)
        async with self._db.begin():
            found = await self._catalog.property(property_id, lock=True)
            if found is None:
                raise NotFoundError
            current = PropertyStatus(found.status)
            if not can_move(current, target):
                raise InvalidTransitionError(f"A {current} property can't become {target}.")
            if target is PropertyStatus.PUBLISHED:
                sellable = await self._catalog.sellable_categories(found.id)
                if problems := publishing_problems(
                    sellable_categories=sellable,
                    verification=VerificationStatus(found.verification_status),
                    verified_only=verified_only,
                ):
                    raise ListingIncompleteError(problems)
                if found.published_at is None:
                    found.published_at = self._clock.now()
            found.status = target
            await self._db.flush()
            await staff_did(
                self._db,
                self._clock,
                actor,
                "catalog.property_status_changed",
                entity="property",
                entity_id=found.public_id,
                **{"from": current.value, "to": target.value},
            )
        return found

    async def set_media(
        self, actor: Actor, property_id: uuid.UUID, media: Sequence[uuid.UUID]
    ) -> None:
        """Make the listing's photos and videos exactly ``media``, in that order; the first is
        the cover. Each must be a listing photo or video that wasn't rejected."""
        if len(media) > MAX_MEDIA:
            raise ListingInvalidError([f"at most {MAX_MEDIA} photos and videos"])
        if len(set(media)) != len(media):
            raise ListingInvalidError(["a photo or video is listed twice"])
        async with self._db.begin():
            found = await self._catalog.property(property_id, lock=True)
            if found is None:
                raise NotFoundError
            refs = await self._media.by_public_id(set(media))
            problems = []
            for media_id in media:
                ref = refs.get(media_id)
                if ref is None:
                    problems.append(f"no such photo or video: {media_id}")
                elif ref.purpose not in _LISTING_MEDIA:
                    problems.append(f"{media_id} isn't a listing photo or video")
                elif ref.status not in {AssetStatus.PROCESSING, AssetStatus.READY}:
                    problems.append(f"{media_id} is {ref.status}")
            check(problems)
            await self._catalog.set_media(found.id, [refs[media_id].id for media_id in media])
            await staff_did(
                self._db,
                self._clock,
                actor,
                "catalog.media_set",
                entity="property",
                entity_id=found.public_id,
                media=[str(media_id) for media_id in media],
            )
