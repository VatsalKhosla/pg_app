"""Catalog persistence (ARCHITECTURE §6). Repositories never commit; the service owns the
transaction.

The public geo queries measure from display points only. The exact point is used to find
duplicates when staff add a listing, and is never returned (domain/location.py).
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from geoalchemy2 import Geography
from sqlalchemy import cast, delete, func, insert, or_, select, update

from app.core import postgis
from app.core.geometry import Point
from app.core.money import Paise
from app.modules.catalog.domain.charges import (
    ChargeKind,
    MandatoryCharge,
    MeteredCharge,
    MonthlyCharge,
    OneTimeCharge,
)
from app.modules.catalog.domain.listing import PropertyStatus
from app.modules.catalog.domain.rooms import BedStatus, CategoryStatus, Occupancy
from app.modules.catalog.models import (
    Amenity,
    Bed,
    Owner,
    Property,
    PropertyAmenity,
    PropertyMedia,
    Room,
    RoomCategory,
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import Collection, Iterable, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.db import Model
    from app.core.geometry import Bounds


def charges_to_json(charges: Iterable[MandatoryCharge]) -> list[dict[str, Any]]:
    stored: list[dict[str, Any]] = []
    for charge in charges:
        match charge:
            case MonthlyCharge():
                stored.append(
                    {
                        "type": "monthly",
                        "kind": charge.kind.value,
                        "label": charge.label,
                        "amount_paise": int(charge.amount),
                    }
                )
            case MeteredCharge():
                stored.append(
                    {
                        "type": "metered",
                        "kind": charge.kind.value,
                        "label": charge.label,
                        "rate_paise": int(charge.rate),
                        "unit": charge.unit,
                        "monthly_estimate_paise": int(charge.monthly_estimate),
                    }
                )
            case OneTimeCharge():
                stored.append(
                    {
                        "type": "one_time",
                        "kind": charge.kind.value,
                        "label": charge.label,
                        "amount_paise": int(charge.amount),
                    }
                )
    return stored


def charges_from_json(stored: Iterable[dict[str, Any]]) -> tuple[MandatoryCharge, ...]:
    charges: list[MandatoryCharge] = []
    for item in stored:
        kind, label = ChargeKind(item["kind"]), str(item["label"])
        match item["type"]:
            case "monthly":
                charges.append(MonthlyCharge(kind, label, Paise(int(item["amount_paise"]))))
            case "metered":
                charges.append(
                    MeteredCharge(
                        kind,
                        label,
                        rate=Paise(int(item["rate_paise"])),
                        unit=str(item["unit"]),
                        monthly_estimate=Paise(int(item["monthly_estimate_paise"])),
                    )
                )
            case "one_time":
                charges.append(OneTimeCharge(kind, label, Paise(int(item["amount_paise"]))))
            case other:
                msg = f"unknown charge type {other!r}"
                raise ValueError(msg)
    return tuple(charges)


def _escape_like(text: str) -> str:
    """``text`` as a literal inside a LIKE pattern."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@dataclass(frozen=True, slots=True)
class NearbyProperty:
    property: Property
    # From the display point.
    distance_m: float


class CatalogRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def add[M: Model](self, row: M) -> M:
        self._db.add(row)
        await self._db.flush()
        return row

    # Owners.

    async def owner(self, public_id: uuid.UUID) -> Owner | None:
        return await self._db.scalar(select(Owner).where(Owner.public_id == public_id))

    async def owner_of_user(self, user_id: int) -> Owner | None:
        return await self._db.scalar(select(Owner).where(Owner.user_id == user_id))

    # Properties.

    async def slugs_from(self, base: str) -> set[str]:
        """``base`` and the numbered slugs made from it that are taken."""
        found = await self._db.scalars(
            select(Property.slug).where(
                or_(Property.slug == base, Property.slug.startswith(f"{base}-", autoescape=True))
            )
        )
        return set(found)

    async def property(self, public_id: uuid.UUID, *, lock: bool = False) -> Property | None:
        query = select(Property).where(Property.public_id == public_id)
        return await self._db.scalar(query.with_for_update() if lock else query)

    async def property_by_slug(self, slug: str) -> Property | None:
        return await self._db.scalar(select(Property).where(Property.slug == slug))

    async def points(self, property_id: int) -> tuple[Point, Point]:
        """The exact and display points."""
        row = (
            await self._db.execute(
                select(
                    postgis.lat(Property.location),
                    postgis.lng(Property.location),
                    postgis.lat(Property.display_location),
                    postgis.lng(Property.display_location),
                ).where(Property.id == property_id)
            )
        ).one()
        return Point(lat=row[0], lng=row[1]), Point(lat=row[2], lng=row[3])

    async def set_points(self, found: Property, exact: Point, display: Point) -> None:
        await self._db.execute(
            update(Property)
            .where(Property.id == found.id)
            .values(location=postgis.point_wkt(exact), display_location=postgis.point_wkt(display))
            .execution_options(synchronize_session=False)
        )
        self._db.expire(found, ["location", "display_location"])

    async def sellable_categories(self, property_id: int) -> int:
        """Active room categories with at least one active bed."""
        query = (
            select(func.count(func.distinct(RoomCategory.id)))
            .join(Room, Room.room_category_id == RoomCategory.id)
            .join(Bed, Bed.room_id == Room.id)
            .where(
                RoomCategory.property_id == property_id,
                RoomCategory.status == CategoryStatus.ACTIVE,
                Bed.status == BedStatus.ACTIVE,
            )
        )
        return await self._db.scalar(query) or 0

    # Room categories, rooms and beds.

    async def category(self, public_id: uuid.UUID) -> RoomCategory | None:
        return await self._db.scalar(
            select(RoomCategory).where(RoomCategory.public_id == public_id)
        )

    async def categories(self, property_id: int) -> list[RoomCategory]:
        found = await self._db.scalars(
            select(RoomCategory)
            .where(RoomCategory.property_id == property_id)
            .order_by(RoomCategory.public_id)
        )
        return list(found)

    async def room_label_taken(self, category_id: int, label: str) -> bool:
        query = select(Room.id).where(Room.room_category_id == category_id, Room.label == label)
        return await self._db.scalar(query) is not None

    async def room(
        self, public_id: uuid.UUID, *, lock: bool = False
    ) -> tuple[Room, Occupancy] | None:
        """A room and its category's occupancy. ``lock`` holds the room until the transaction
        ends, so two beds can't both take its last place."""
        query = (
            select(Room, RoomCategory.occupancy)
            .join(RoomCategory, RoomCategory.id == Room.room_category_id)
            .where(Room.public_id == public_id)
        )
        found = (await self._db.execute(query.with_for_update(of=Room) if lock else query)).first()
        return None if found is None else (found[0], Occupancy(found[1]))

    async def beds_in(self, room_id: int) -> list[Bed]:
        found = await self._db.scalars(
            select(Bed).where(Bed.room_id == room_id).order_by(Bed.public_id)
        )
        return list(found)

    async def rooms_of(self, category_ids: Collection[int]) -> list[Room]:
        if not category_ids:
            return []
        found = await self._db.scalars(
            select(Room)
            .where(Room.room_category_id.in_(category_ids))
            .order_by(Room.room_category_id, Room.label, Room.public_id)
        )
        return list(found)

    async def beds_of(self, room_ids: Collection[int]) -> list[Bed]:
        if not room_ids:
            return []
        found = await self._db.scalars(
            select(Bed).where(Bed.room_id.in_(room_ids)).order_by(Bed.room_id, Bed.label)
        )
        return list(found)

    async def category_for_update(self, public_id: uuid.UUID) -> RoomCategory | None:
        return await self._db.scalar(
            select(RoomCategory).where(RoomCategory.public_id == public_id).with_for_update()
        )

    async def bed(self, public_id: uuid.UUID, *, lock: bool = False) -> Bed | None:
        query = select(Bed).where(Bed.public_id == public_id)
        return await self._db.scalar(query.with_for_update() if lock else query)

    async def property_of_category(self, category_id: int) -> Property:
        found = await self._db.scalar(
            select(Property)
            .join(RoomCategory, RoomCategory.property_id == Property.id)
            .where(RoomCategory.id == category_id)
        )
        if found is None:  # pragma: no cover - a category always has its property
            raise LookupError(category_id)
        return found

    async def property_of_room(self, room_id: int) -> Property:
        found = await self._db.scalar(
            select(Property)
            .join(RoomCategory, RoomCategory.property_id == Property.id)
            .join(Room, Room.room_category_id == RoomCategory.id)
            .where(Room.id == room_id)
        )
        if found is None:  # pragma: no cover - a room always has its property
            raise LookupError(room_id)
        return found

    # Pages, for staff: by public id, ``limit + 1`` rows, so the caller sees whether more follow.

    async def owners_page(
        self,
        *,
        after: uuid.UUID | None,
        limit: int,
        text: str | None = None,
        user_id: int | None = None,
    ) -> list[Owner]:
        query = select(Owner).order_by(Owner.public_id).limit(limit + 1)
        if after is not None:
            query = query.where(Owner.public_id > after)
        if user_id is not None:
            query = query.where(Owner.user_id == user_id)
        elif text:
            pattern = f"%{_escape_like(text)}%"
            query = query.where(
                or_(
                    Owner.business_name.ilike(pattern, escape="\\"),
                    Owner.legal_name.ilike(pattern, escape="\\"),
                )
            )
        return list(await self._db.scalars(query))

    async def properties_page(
        self,
        *,
        after: uuid.UUID | None,
        limit: int,
        status: PropertyStatus | None = None,
        text: str | None = None,
    ) -> list[Property]:
        query = select(Property).order_by(Property.public_id).limit(limit + 1)
        if after is not None:
            query = query.where(Property.public_id > after)
        if status is not None:
            query = query.where(Property.status == status)
        if text:
            query = query.where(Property.name.ilike(f"%{_escape_like(text)}%", escape="\\"))
        return list(await self._db.scalars(query))

    async def owners_by_id(self, ids: Collection[int]) -> dict[int, Owner]:
        if not ids:
            return {}
        return {
            owner.id: owner
            for owner in await self._db.scalars(select(Owner).where(Owner.id.in_(ids)))
        }

    # Media.

    async def media_of(self, property_ids: Collection[int]) -> dict[int, list[int]]:
        """Each property's media assets (internal ids), in page order."""
        if not property_ids:
            return {}
        rows = await self._db.execute(
            select(PropertyMedia.property_id, PropertyMedia.media_asset_id)
            .where(PropertyMedia.property_id.in_(property_ids))
            .order_by(PropertyMedia.property_id, PropertyMedia.position)
        )
        media: dict[int, list[int]] = {}
        for property_id, asset_id in rows:
            media.setdefault(property_id, []).append(asset_id)
        return media

    async def set_media(self, property_id: int, asset_ids: Sequence[int]) -> None:
        await self._db.execute(
            delete(PropertyMedia).where(PropertyMedia.property_id == property_id)
        )
        if asset_ids:
            await self._db.execute(
                insert(PropertyMedia),
                [
                    {"property_id": property_id, "media_asset_id": asset_id, "position": position}
                    for position, asset_id in enumerate(asset_ids)
                ],
            )

    # Amenities.

    async def amenity_ids(self, slugs: Collection[str]) -> dict[str, int]:
        rows = await self._db.execute(
            select(Amenity.slug, Amenity.id).where(Amenity.slug.in_(slugs))
        )
        return {row.slug: row.id for row in rows}

    async def set_amenities(self, property_id: int, amenity_ids: Collection[int]) -> None:
        await self._db.execute(
            delete(PropertyAmenity).where(PropertyAmenity.property_id == property_id)
        )
        if amenity_ids:
            await self._db.execute(
                insert(PropertyAmenity),
                [
                    {"property_id": property_id, "amenity_id": amenity_id}
                    for amenity_id in sorted(amenity_ids)
                ],
            )

    async def all_amenities(self) -> list[Amenity]:
        return list(await self._db.scalars(select(Amenity).order_by(Amenity.name)))

    async def amenities_of(self, property_id: int) -> list[str]:
        found = await self._db.scalars(
            select(Amenity.slug)
            .join(PropertyAmenity, PropertyAmenity.amenity_id == Amenity.id)
            .where(PropertyAmenity.property_id == property_id)
            .order_by(Amenity.slug)
        )
        return list(found)

    # Where properties are.

    async def within(
        self,
        center: Point,
        radius_m: float,
        *,
        statuses: Collection[PropertyStatus] = (PropertyStatus.PUBLISHED,),
    ) -> list[NearbyProperty]:
        """Properties whose display point is within ``radius_m`` of ``center``, nearest first."""
        here = postgis.geography(center)
        distance = postgis.distance(Property.display_location, here)
        rows = await self._db.execute(
            select(Property, distance)
            .where(
                func.ST_DWithin(Property.display_location, here, radius_m),
                Property.status.in_(statuses),
            )
            .order_by(distance, Property.public_id)
        )
        return [NearbyProperty(property=found, distance_m=metres) for found, metres in rows]

    async def in_bounds(
        self,
        bounds: Bounds,
        *,
        statuses: Collection[PropertyStatus] = (PropertyStatus.PUBLISHED,),
    ) -> list[Property]:
        """Properties whose display point is inside the box, as for a map's view."""
        box = cast(
            func.ST_MakeEnvelope(bounds.west, bounds.south, bounds.east, bounds.north, 4326),
            Geography,
        )
        found = await self._db.scalars(
            select(Property)
            .where(func.ST_Intersects(Property.display_location, box))
            .where(Property.status.in_(statuses))
            .order_by(Property.public_id)
        )
        return list(found)

    async def near_exact(self, point: Point, radius_m: float) -> list[Property]:
        """Every property whose exact point is within ``radius_m``: likely the same building,
        listed twice. For staff only."""
        found = await self._db.scalars(
            select(Property)
            .where(func.ST_DWithin(Property.location, postgis.geography(point), radius_m))
            .order_by(Property.public_id)
        )
        return list(found)
