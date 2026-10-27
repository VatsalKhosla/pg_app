"""Catalog persistence (ARCHITECTURE §6). Repositories never commit; the service owns the
transaction.

The public geo queries measure from display points only. The exact point is used to find
duplicates when staff add a listing, and is never returned (domain/location.py).
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NamedTuple

from geoalchemy2 import Geography
from sqlalchemy import and_, cast, delete, func, insert, or_, select, update

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
from app.modules.catalog.domain.listing import PropertyStatus, SocietyPermission
from app.modules.catalog.domain.rooms import BedStatus, CategoryStatus, Occupancy
from app.modules.catalog.domain.verification import (
    Checklist,
    Condition,
    Cracks,
    VisitStatus,
    WomenSafety,
)
from app.modules.catalog.models import (
    Amenity,
    Bed,
    Owner,
    OwnerAgreement,
    Property,
    PropertyAmenity,
    PropertyMedia,
    Room,
    RoomCategory,
    VerificationPhoto,
    VerificationVisit,
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import Collection, Iterable, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.db import AppendOnlyModel
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


def checklist_to_json(checklist: Checklist) -> dict[str, Any]:
    return {
        "building_age_years": checklist.building_age_years,
        "condition": checklist.condition.value,
        "cracks": checklist.cracks.value,
        "exits": checklist.exits,
        "fire_extinguishers": checklist.fire_extinguishers,
        "cctv": checklist.cctv,
        "warden": checklist.warden,
        "women_safety": sorted(feature.value for feature in checklist.women_safety),
        "licence_number": checklist.licence_number,
        "society_permission": checklist.society_permission.value,
        "authority_notice": checklist.authority_notice,
    }


def checklist_from_json(stored: dict[str, Any]) -> Checklist:
    return Checklist(
        building_age_years=stored["building_age_years"],
        condition=Condition(stored["condition"]),
        cracks=Cracks(stored["cracks"]),
        exits=stored["exits"],
        fire_extinguishers=stored["fire_extinguishers"],
        cctv=stored["cctv"],
        warden=stored["warden"],
        women_safety=frozenset(WomenSafety(feature) for feature in stored["women_safety"]),
        licence_number=stored["licence_number"],
        society_permission=SocietyPermission(stored["society_permission"]),
        authority_notice=stored["authority_notice"],
    )


def _escape_like(text: str) -> str:
    """``text`` as a literal inside a LIKE pattern."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@dataclass(frozen=True, slots=True)
class NearbyProperty:
    property: Property
    # From the display point.
    distance_m: float


class RentRow(NamedTuple):
    category_id: int
    base_rent_paise: int
    active_beds: int
    occupancy: str
    ac: bool
    attached_bath: bool


class CatalogRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def add[M: AppendOnlyModel](self, row: M) -> M:
        self._db.add(row)
        await self._db.flush()
        return row

    # Owners.

    async def owner(self, public_id: uuid.UUID, *, lock: bool = False) -> Owner | None:
        query = select(Owner).where(Owner.public_id == public_id)
        return await self._db.scalar(query.with_for_update() if lock else query)

    async def owner_of_user(self, user_id: int, *, lock: bool = False) -> Owner | None:
        query = select(Owner).where(Owner.user_id == user_id)
        return await self._db.scalar(query.with_for_update() if lock else query)

    async def acceptances(
        self, owner_id: int, *, version: str | None = None
    ) -> list[OwnerAgreement]:
        """An owner's agreement acceptances (of ``version``, if given), newest first: one per
        version they accepted, so a handful."""
        query = select(OwnerAgreement).where(OwnerAgreement.owner_id == owner_id)
        if version is not None:
            query = query.where(OwnerAgreement.version == version)
        rows = await self._db.scalars(
            query.order_by(OwnerAgreement.accepted_at.desc(), OwnerAgreement.id.desc())
        )
        return list(rows)

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

    async def property_by_id(self, property_id: int, *, lock: bool = False) -> Property:
        """A property another row points at, so it exists."""
        query = select(Property).where(Property.id == property_id)
        return (await self._db.execute(query.with_for_update() if lock else query)).scalar_one()

    async def properties_by_id(self, ids: Collection[int]) -> dict[int, Property]:
        if not ids:
            return {}
        rows = await self._db.scalars(select(Property).where(Property.id.in_(ids)))
        return {row.id: row for row in rows}

    async def visit_ids_of(self, property_id: int) -> list[uuid.UUID]:
        """The public ids of a property's verification visits."""
        rows = await self._db.scalars(
            select(VerificationVisit.public_id).where(VerificationVisit.property_id == property_id)
        )
        return list(rows)

    async def exact_points(self, ids: Collection[int]) -> dict[int, Point]:
        """Each property's exact point, which only staff see."""
        if not ids:
            return {}
        rows = await self._db.execute(
            select(
                Property.id, postgis.lat(Property.location), postgis.lng(Property.location)
            ).where(Property.id.in_(ids))
        )
        return {row_id: Point(lat=lat, lng=lng) for row_id, lat, lng in rows}

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

    async def display_point(self, property_id: int) -> Point:
        """The display point alone: what public reads ask for, so they never hold the exact one."""
        row = (
            await self._db.execute(
                select(
                    postgis.lat(Property.display_location), postgis.lng(Property.display_location)
                ).where(Property.id == property_id)
            )
        ).one()
        return Point(lat=row[0], lng=row[1])

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

    async def category_rents(self, property_id: int) -> list[RentRow]:
        """Each active room category with a bed to sell: its id, base rent, active beds,
        occupancy, AC and attached bath. What other modules price, count and filter by."""
        active_beds = func.count(Bed.id).filter(Bed.status == BedStatus.ACTIVE)
        rows = await self._db.execute(
            select(
                RoomCategory.id,
                RoomCategory.base_rent_paise,
                active_beds,
                RoomCategory.occupancy,
                RoomCategory.ac,
                RoomCategory.attached_bath,
            )
            .join(Room, Room.room_category_id == RoomCategory.id)
            .join(Bed, Bed.room_id == Room.id)
            .where(
                RoomCategory.property_id == property_id,
                RoomCategory.status == CategoryStatus.ACTIVE,
            )
            .group_by(RoomCategory.id)
            .having(active_beds > 0)
            .order_by(RoomCategory.id)
        )
        return [RentRow(*row) for row in rows]

    async def property_ids_after(self, after: int | None, *, limit: int) -> list[int]:
        """Properties' internal ids in order, a page at a time."""
        query = select(Property.id).order_by(Property.id).limit(limit)
        if after is not None:
            query = query.where(Property.id > after)
        return list(await self._db.scalars(query))

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

    async def property_amenities(self, property_id: int) -> list[Amenity]:
        found = await self._db.scalars(
            select(Amenity)
            .join(PropertyAmenity, PropertyAmenity.amenity_id == Amenity.id)
            .where(PropertyAmenity.property_id == property_id)
            .order_by(Amenity.name)
        )
        return list(found)

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


class VisitRepository:
    """Verification visits and their photos (ADR 0024)."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def visit(self, public_id: uuid.UUID, *, lock: bool = False) -> VerificationVisit | None:
        query = select(VerificationVisit).where(VerificationVisit.public_id == public_id)
        return await self._db.scalar(query.with_for_update() if lock else query)

    async def position(self, visit_id: int) -> Point | None:
        """Where the agent's phone said they were, once the report is in."""
        row = (
            await self._db.execute(
                select(
                    postgis.lat(VerificationVisit.position),
                    postgis.lng(VerificationVisit.position),
                ).where(VerificationVisit.id == visit_id, VerificationVisit.position.is_not(None))
            )
        ).one_or_none()
        return None if row is None else Point(lat=row[0], lng=row[1])

    async def positions(self, visit_ids: Collection[int]) -> dict[int, Point]:
        if not visit_ids:
            return {}
        rows = await self._db.execute(
            select(
                VerificationVisit.id,
                postgis.lat(VerificationVisit.position),
                postgis.lng(VerificationVisit.position),
            ).where(VerificationVisit.id.in_(visit_ids), VerificationVisit.position.is_not(None))
        )
        return {visit_id: Point(lat=lat, lng=lng) for visit_id, lat, lng in rows}

    async def set_position(self, visit: VerificationVisit, point: Point) -> None:
        await self._db.execute(
            update(VerificationVisit)
            .where(VerificationVisit.id == visit.id)
            .values(position=postgis.point_wkt(point))
            .execution_options(synchronize_session=False)
        )
        self._db.expire(visit, ["position"])

    async def of_property(
        self, property_id: int, *, before: uuid.UUID | None, limit: int
    ) -> list[VerificationVisit]:
        """A property's visits, newest first: ``limit + 1`` at most, so the caller can tell
        whether another page follows."""
        query = (
            select(VerificationVisit)
            .where(VerificationVisit.property_id == property_id)
            .order_by(VerificationVisit.public_id.desc())
            .limit(limit + 1)
        )
        if before is not None:
            query = query.where(VerificationVisit.public_id < before)
        return list(await self._db.scalars(query))

    async def page(
        self,
        *,
        after: uuid.UUID | None,
        limit: int,
        agent_id: int | None = None,
        status: VisitStatus | None = None,
    ) -> list[VerificationVisit]:
        """Visits by when they're booked for, soonest first, then by public id: ``limit + 1``
        at most. ``after`` is the last visit of the previous page."""
        query = (
            select(VerificationVisit)
            .order_by(VerificationVisit.scheduled_for, VerificationVisit.public_id)
            .limit(limit + 1)
        )
        if agent_id is not None:
            query = query.where(VerificationVisit.agent_id == agent_id)
        if status is not None:
            query = query.where(VerificationVisit.status == status)
        if after is not None:
            anchor = await self.visit(after)
            if anchor is None:
                return []
            query = query.where(
                or_(
                    VerificationVisit.scheduled_for > anchor.scheduled_for,
                    and_(
                        VerificationVisit.scheduled_for == anchor.scheduled_for,
                        VerificationVisit.public_id > anchor.public_id,
                    ),
                )
            )
        return list(await self._db.scalars(query))

    async def photos_of(self, visit_ids: Collection[int]) -> dict[int, list[int]]:
        """Each visit's photos (media asset ids), in the order taken."""
        if not visit_ids:
            return {}
        rows = await self._db.execute(
            select(VerificationPhoto.visit_id, VerificationPhoto.media_asset_id)
            .where(VerificationPhoto.visit_id.in_(visit_ids))
            .order_by(VerificationPhoto.visit_id, VerificationPhoto.position)
        )
        photos: dict[int, list[int]] = {}
        for visit_id, asset_id in rows:
            photos.setdefault(visit_id, []).append(asset_id)
        return photos

    async def add_photos(self, visit_id: int, asset_ids: Sequence[int]) -> None:
        if asset_ids:
            await self._db.execute(
                insert(VerificationPhoto),
                [
                    {"visit_id": visit_id, "media_asset_id": asset_id, "position": position}
                    for position, asset_id in enumerate(asset_ids)
                ],
            )
