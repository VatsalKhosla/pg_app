"""What staff see of the catalog (step 2.4): the listings, one listing in full (the exact point and
the address included, which only staff see), and its audit trail.

Each read takes a fixed number of queries however many rows: one per level, never one per row.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from app.core import audit
from app.core.errors import NotFoundError
from app.core.flags import Flag
from app.core.pagination import split_page
from app.modules.catalog.domain.listing import (
    PropertyStatus,
    VerificationStatus,
    publishing_problems,
)
from app.modules.catalog.repository import CatalogRepository, charges_from_json
from app.modules.catalog.service.owners import OwnerRecord
from app.modules.geo.service import GeoLookup
from app.modules.identity.service import Accounts
from app.modules.media.service import MediaLookup

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.audit import AuditLog
    from app.core.flags import FlagReader
    from app.core.geometry import Point
    from app.core.pagination import PageRequest
    from app.modules.catalog.domain.charges import MandatoryCharge
    from app.modules.catalog.models import Amenity, Bed, Property, Room, RoomCategory
    from app.modules.geo.service import LocalityRef
    from app.modules.media.service import Buckets, MediaRef


# Pins this close are probably the same building, listed twice.
DUPLICATE_RADIUS_M: Final = 30.0


@dataclass(frozen=True, slots=True)
class RoomView:
    room: Room
    beds: tuple[Bed, ...]


@dataclass(frozen=True, slots=True)
class CategoryView:
    category: RoomCategory
    charges: tuple[MandatoryCharge, ...]
    rooms: tuple[RoomView, ...]


@dataclass(frozen=True, slots=True)
class ListingSummary:
    property: Property
    locality: LocalityRef
    cover: MediaRef | None


@dataclass(frozen=True, slots=True)
class ListingDetail:
    property: Property
    owner: OwnerRecord
    locality: LocalityRef
    exact: Point
    display: Point
    categories: tuple[CategoryView, ...]
    amenities: tuple[str, ...]
    media: tuple[MediaRef, ...]
    # What stops it being published now; empty when nothing does.
    problems: tuple[str, ...]


class CatalogReader:
    def __init__(self, db: AsyncSession, *, buckets: Buckets, flags: FlagReader) -> None:
        self._db = db
        self._flags = flags
        self._catalog = CatalogRepository(db)
        self._geo = GeoLookup(db)
        self._media = MediaLookup(db, buckets)
        self._accounts = Accounts(db)

    async def amenities(self) -> list[Amenity]:
        async with self._db.begin():
            return await self._catalog.all_amenities()

    async def listings(
        self,
        request: PageRequest,
        *,
        status: PropertyStatus | None = None,
        text: str | None = None,
    ) -> tuple[list[ListingSummary], uuid.UUID | None]:
        async with self._db.begin():
            rows = await self._catalog.properties_page(
                after=request.after, limit=request.limit, status=status, text=text
            )
            found, next_cursor = split_page(rows, request, cursor_of=lambda row: row.public_id)
            localities = await self._geo.localities({row.locality_id for row in found})
            media = await self._catalog.media_of([row.id for row in found])
            covers = await self._media.by_id([ids[0] for ids in media.values() if ids])
        return [
            ListingSummary(
                property=row,
                locality=localities[row.locality_id],
                cover=covers.get(media[row.id][0]) if media.get(row.id) else None,
            )
            for row in found
        ], next_cursor

    async def listing(self, property_id: uuid.UUID) -> ListingDetail:
        verified_only = await self._flags.is_enabled(Flag.VERIFIED_ONLY)
        async with self._db.begin():
            found = await self._catalog.property(property_id)
            if found is None:
                raise NotFoundError
            exact, display = await self._catalog.points(found.id)
            owner = (await self._catalog.owners_by_id([found.owner_id]))[found.owner_id]
            accounts = await self._accounts.many([owner.user_id])
            locality = (await self._geo.localities([found.locality_id]))[found.locality_id]
            categories = await self._catalog.categories(found.id)
            rooms = await self._catalog.rooms_of([category.id for category in categories])
            beds = await self._catalog.beds_of([room.id for room in rooms])
            amenities = await self._catalog.amenities_of(found.id)
            media_ids = (await self._catalog.media_of([found.id])).get(found.id, [])
            media = await self._media.by_id(media_ids)
            sellable = await self._catalog.sellable_categories(found.id)
        beds_by_room: dict[int, list[Bed]] = {}
        for bed in beds:
            beds_by_room.setdefault(bed.room_id, []).append(bed)
        rooms_by_category: dict[int, list[RoomView]] = {}
        for room in rooms:
            rooms_by_category.setdefault(room.room_category_id, []).append(
                RoomView(room, tuple(beds_by_room.get(room.id, ())))
            )
        return ListingDetail(
            property=found,
            owner=OwnerRecord(owner, accounts.get(owner.user_id)),
            locality=locality,
            exact=exact,
            display=display,
            categories=tuple(
                CategoryView(
                    category,
                    charges_from_json(category.mandatory_charges),
                    tuple(rooms_by_category.get(category.id, ())),
                )
                for category in categories
            ),
            amenities=tuple(amenities),
            media=tuple(media[media_id] for media_id in media_ids if media_id in media),
            problems=tuple(
                publishing_problems(
                    sellable_categories=sellable,
                    verification=VerificationStatus(found.verification_status),
                    verified_only=verified_only,
                )
            ),
        )

    async def history(self, property_id: uuid.UUID) -> list[AuditLog]:
        """Everything done to the listing, its rooms, its beds and its verification visits,
        newest first."""
        async with self._db.begin():
            found = await self._catalog.property(property_id)
            if found is None:
                raise NotFoundError
            categories = await self._catalog.categories(found.id)
            rooms = await self._catalog.rooms_of([category.id for category in categories])
            beds = await self._catalog.beds_of([room.id for room in rooms])
            visits = await self._catalog.visit_ids_of(found.id)
            entity_ids = {
                str(found.public_id),
                *(str(category.public_id) for category in categories),
                *(str(room.public_id) for room in rooms),
                *(str(bed.public_id) for bed in beds),
                *(str(visit) for visit in visits),
            }
            return await audit.trail(self._db, entity_ids=entity_ids)

    async def listing_of(
        self,
        *,
        category: uuid.UUID | None = None,
        room: uuid.UUID | None = None,
        bed: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """The listing a category, room or bed belongs to."""
        async with self._db.begin():
            if category is not None:
                found_category = await self._catalog.category(category)
                if found_category is None:
                    raise NotFoundError
                return (await self._catalog.property_of_category(found_category.id)).public_id
            room_id = None
            if room is not None:
                found_room = await self._catalog.room(room)
                room_id = None if found_room is None else found_room[0].id
            elif bed is not None:
                found_bed = await self._catalog.bed(bed)
                room_id = None if found_bed is None else found_bed.room_id
            if room_id is None:
                raise NotFoundError
            return (await self._catalog.property_of_room(room_id)).public_id

    async def duplicates_of(self, property_id: uuid.UUID) -> list[uuid.UUID]:
        """Other listings whose exact pin is within 30 m: likely the same building twice."""
        async with self._db.begin():
            found = await self._catalog.property(property_id)
            if found is None:
                raise NotFoundError
            exact, _ = await self._catalog.points(found.id)
            near = await self._catalog.near_exact(exact, DUPLICATE_RADIUS_M)
        return [other.public_id for other in near if other.id != found.id]
