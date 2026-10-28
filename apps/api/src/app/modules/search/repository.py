"""Reads and writes of the search module's own tables."""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Float,
    Text,
    column,
    delete,
    func,
    insert,
    literal,
    or_,
    select,
    true,
    tuple_,
    values,
)
from sqlalchemy.dialects.postgresql import insert as upsert

from app.core import postgis
from app.core.geometry import Point
from app.modules.search.domain.query import Order
from app.modules.search.models import PropertyPriceSummary, SearchListing

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence
    from datetime import date

    from sqlalchemy import ColumnElement, SQLColumnExpression
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql.selectable import LateralFromClause

    from app.core.geometry import Bounds
    from app.modules.catalog.service import SearchEntry
    from app.modules.search.domain.query import Cursor
    from app.modules.search.domain.summaries import MonthSummary


class SummaryRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def replace(
        self, property_id: int, summaries: Sequence[MonthSummary], *, computed_at: datetime
    ) -> None:
        """A property's summaries, all at once: readers see the old set or the new one."""
        await self._db.execute(
            delete(PropertyPriceSummary).where(PropertyPriceSummary.property_id == property_id)
        )
        if summaries:
            await self._db.execute(
                insert(PropertyPriceSummary),
                [
                    {
                        "property_id": property_id,
                        "room_category_id": summary.category_id,
                        "month": summary.month,
                        "min_rent_paise": summary.min_rent,
                        "max_rent_paise": summary.max_rent,
                        "available_beds": summary.available_beds,
                        "occupancy": summary.occupancy,
                        "ac": summary.ac,
                        "attached_bath": summary.attached_bath,
                        "computed_at": computed_at,
                    }
                    for summary in summaries
                ],
            )

    async def of_property(self, property_id: int) -> list[PropertyPriceSummary]:
        found = await self._db.scalars(
            select(PropertyPriceSummary)
            .where(PropertyPriceSummary.property_id == property_id)
            .order_by(PropertyPriceSummary.room_category_id, PropertyPriceSummary.month)
        )
        return list(found)


@dataclass(frozen=True, slots=True)
class Filters:
    """A search, as the query needs it: places already looked up, the month decided."""

    month: date
    campus: Point | None = None
    radius_m: int = 0
    locality_id: int | None = None
    bbox: Bounds | None = None
    budget_min: int | None = None
    budget_max: int | None = None
    gender: str | None = None
    occupancy: str | None = None
    meals: str | None = None
    ac: bool = False
    attached_bath: bool = False
    amenities: tuple[str, ...] = ()
    verified_only: bool = True
    available: bool = False
    text: str | None = None


@dataclass(frozen=True, slots=True)
class Hit:
    """One listing in the results, with what its categories that match come to that month."""

    property_id: int
    public_id: uuid.UUID
    slug: str
    name: str
    locality_slug: str
    locality_name: str
    display: Point
    gender_policy: str
    meals: str
    verified: bool
    licensed: bool
    media_ids: tuple[int, ...]
    min_rent: int
    max_rent: int
    beds_free: int
    # From the chosen campus to the display point, in metres; None without a campus.
    distance_m: float | None
    # Its place in the order, for the next page's cursor.
    key: int | float | str


class SearchRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def put(
        self,
        property_id: int,
        entry: SearchEntry,
        *,
        refreshed_at: datetime,
        changed_at: datetime | None = None,
    ) -> None:
        """The listing's entry, made or brought up to date; ``changed_at`` only when the catalog
        said it changed (the nightly refresh keeps the last one)."""
        row: dict[str, Any] = {
            "public_id": entry.public_id,
            "slug": entry.slug,
            "name": entry.name,
            "locality_id": entry.locality.id,
            "locality_slug": entry.locality.slug,
            "locality_name": entry.locality.name,
            "display_location": postgis.point_wkt(entry.display),
            "gender_policy": entry.gender_policy.value,
            "meals": entry.meals.value,
            "verified": entry.verified,
            "licensed": entry.licensed,
            "amenities": list(entry.amenities),
            "media_ids": list(entry.media_ids),
            "published_at": entry.published_at,
            "refreshed_at": refreshed_at,
        }
        if changed_at is not None:
            row["changed_at"] = changed_at
        await self._db.execute(
            upsert(SearchListing)
            .values(property_id=property_id, **row)
            .on_conflict_do_update(index_elements=[SearchListing.property_id], set_=row)
        )

    async def remove(self, property_id: int) -> None:
        await self._db.execute(
            delete(SearchListing).where(SearchListing.property_id == property_id)
        )

    async def slug(self, property_id: int) -> str | None:
        """The listing's slug as search has it, if search has it."""
        return await self._db.scalar(
            select(SearchListing.slug).where(SearchListing.property_id == property_id)
        )

    async def places_by_locality(self, filters: Filters) -> list[PlaceRow]:
        """Each locality with listings that match: how many, and their rents' range."""
        matching = _matching_categories(filters)
        listing = SearchListing
        rows = await self._db.execute(
            select(
                listing.locality_slug,
                listing.locality_name,
                func.count(),
                func.min(matching.c.min_rent),
                func.max(matching.c.max_rent),
            )
            .select_from(listing)
            .join(matching, true())
            .where(*_listing_conditions(filters), matching.c.min_rent.is_not(None))
            .group_by(listing.locality_slug, listing.locality_name)
        )
        return [PlaceRow(*row) for row in rows]

    async def places_near(
        self, campuses: Sequence[tuple[str, str, Point]], filters: Filters, *, radius_m: int
    ) -> list[PlaceRow]:
        """Each campus (slug, name, location) with listings that match within ``radius_m``: one
        query, each campus's reach found through the display points' index."""
        if not campuses:
            return []
        campus = values(
            column("slug", Text),
            column("name", Text),
            column("lat", Float),
            column("lng", Float),
            name="campus",
        ).data([(slug, name, point.lat, point.lng) for slug, name, point in campuses])
        at = func.geography(func.ST_SetSRID(func.ST_MakePoint(campus.c.lng, campus.c.lat), 4326))
        matching = _matching_categories(filters)
        listing = SearchListing
        rows = await self._db.execute(
            select(
                campus.c.slug,
                campus.c.name,
                func.count(),
                func.min(matching.c.min_rent),
                func.max(matching.c.max_rent),
            )
            .select_from(campus)
            .join(listing, func.ST_DWithin(listing.display_location, at, radius_m))
            .join(matching, true())
            .where(*_listing_conditions(filters), matching.c.min_rent.is_not(None))
            .group_by(campus.c.slug, campus.c.name)
        )
        return [PlaceRow(*row) for row in rows]

    async def sitemap(
        self, *, verified_only: bool, after: uuid.UUID | None, limit: int
    ) -> list[SitemapRow]:
        """Listings in public-id order, ``limit + 1`` of them (the extra one says there's more):
        when each last changed, or was published if it hasn't since."""
        listing = SearchListing
        conditions: list[ColumnElement[bool]] = []
        if verified_only:
            conditions.append(listing.verified.is_(True))
        if after is not None:
            conditions.append(listing.public_id > after)
        rows = await self._db.execute(
            select(
                listing.public_id,
                listing.slug,
                func.coalesce(listing.changed_at, listing.published_at),
            )
            .where(*conditions)
            .order_by(listing.public_id)
            .limit(limit + 1)
        )
        return [SitemapRow(*row) for row in rows]

    async def search(
        self, filters: Filters, *, order: Order, cursor: Cursor | None, limit: int
    ) -> list[Hit]:
        """One page of listings, ``limit + 1`` of them (the extra one says there's another
        page), in one query however many match."""
        matching = _matching_categories(filters)
        listing = SearchListing
        distance = (
            None
            if filters.campus is None
            else postgis.distance(listing.display_location, postgis.geography(filters.campus))
        )
        # Only listings with a category that matches.
        conditions = [*_listing_conditions(filters), matching.c.min_rent.is_not(None)]
        relevance = None
        if filters.text is not None:
            match, relevance = _text(filters.text)
            conditions.append(match)
        keys: dict[Order, SQLColumnExpression[Any] | None] = {
            Order.RELEVANCE: relevance,
            Order.PRICE_ASC: matching.c.min_rent,
            Order.PRICE_DESC: matching.c.min_rent,
            Order.DISTANCE: distance,
            Order.NEWEST: listing.published_at,
        }
        key = keys[order]
        if key is None:  # pragma: no cover - the service picks orders the request supports
            msg = f"can't order by {order} for this search"
            raise ValueError(msg)
        ascending = order in {Order.PRICE_ASC, Order.DISTANCE}
        if cursor is not None:
            last = datetime.fromisoformat(str(cursor.key)) if order is Order.NEWEST else cursor.key
            position = tuple_(key, listing.public_id)
            after = tuple_(literal(last), literal(cursor.after))
            conditions.append(position > after if ascending else position < after)
        query = (
            select(
                listing.property_id,
                listing.public_id,
                listing.slug,
                listing.name,
                listing.locality_slug,
                listing.locality_name,
                postgis.lat(listing.display_location),
                postgis.lng(listing.display_location),
                listing.gender_policy,
                listing.meals,
                listing.verified,
                listing.licensed,
                listing.media_ids,
                matching.c.min_rent,
                matching.c.max_rent,
                matching.c.beds_free,
                literal(None, Float) if distance is None else distance,
                key,
            )
            .select_from(listing)
            .join(matching, true())
            .where(*conditions)
            .order_by(
                *(
                    (key.asc(), listing.public_id.asc())
                    if ascending
                    else (key.desc(), listing.public_id.desc())
                )
            )
            .limit(limit + 1)
        )
        return [_hit(tuple(row)) for row in await self._db.execute(query)]

    async def pins(self, filters: Filters, *, limit: int) -> list[PinRow]:
        """Every listing that matches, as a pin, ``limit`` at most: one query, in a stable order."""
        matching = _matching_categories(filters)
        listing = SearchListing
        conditions = [*_listing_conditions(filters), matching.c.min_rent.is_not(None)]
        if filters.text is not None:
            conditions.append(_text(filters.text)[0])
        rows = await self._db.execute(
            select(
                listing.public_id,
                listing.slug,
                postgis.lat(listing.display_location),
                postgis.lng(listing.display_location),
                matching.c.min_rent,
                matching.c.max_rent,
                listing.gender_policy,
                listing.verified,
                matching.c.beds_free,
            )
            .select_from(listing)
            .join(matching, true())
            .where(*conditions)
            .order_by(listing.public_id)
            .limit(limit)
        )
        return [
            PinRow(
                public_id=public_id,
                slug=slug,
                display=Point(lat=lat, lng=lng),
                min_rent=low,
                max_rent=high,
                gender_policy=gender,
                verified=verified,
                beds_free=int(beds),
            )
            for public_id, slug, lat, lng, low, high, gender, verified, beds in rows
        ]


@dataclass(frozen=True, slots=True)
class PlaceRow:
    slug: str
    name: str
    listings: int
    min_rent: int
    max_rent: int


@dataclass(frozen=True, slots=True)
class SitemapRow:
    public_id: uuid.UUID
    slug: str
    changed_at: datetime


@dataclass(frozen=True, slots=True)
class PinRow:
    public_id: uuid.UUID
    slug: str
    display: Point
    min_rent: int
    max_rent: int
    gender_policy: str
    verified: bool
    beds_free: int


def _text(text: str) -> tuple[ColumnElement[bool], ColumnElement[float]]:
    """Whole words (full text) or near misses (trigrams), and how well each listing matches."""
    listing = SearchListing
    words = func.plainto_tsquery("simple", text)
    match = or_(listing.search_vector.op("@@")(words), literal(text).op("<%")(listing.search_text))
    relevance = (
        func.ts_rank(listing.search_vector, words) + func.word_similarity(text, listing.search_text)
    ).cast(Float)
    return match, relevance


def _matching_categories(filters: Filters) -> LateralFromClause:
    """For each listing, its room categories that match the search in the month: their rents'
    range and free beds (all null when none match). A lateral lookup by listing and month, so
    the work grows with the listings the other filters leave, whatever the planner guesses."""
    summary = PropertyPriceSummary
    conditions: list[ColumnElement[bool]] = [
        summary.property_id == SearchListing.property_id,
        summary.month == filters.month,
    ]
    if filters.occupancy is not None:
        conditions.append(summary.occupancy == filters.occupancy)
    if filters.ac:
        conditions.append(summary.ac.is_(True))
    if filters.attached_bath:
        conditions.append(summary.attached_bath.is_(True))
    # A category's range for the month overlaps the budget.
    if filters.budget_min is not None:
        conditions.append(summary.max_rent_paise >= filters.budget_min)
    if filters.budget_max is not None:
        conditions.append(summary.min_rent_paise <= filters.budget_max)
    if filters.available:
        conditions.append(summary.available_beds > 0)
    return (
        select(
            func.min(summary.min_rent_paise).label("min_rent"),
            func.max(summary.max_rent_paise).label("max_rent"),
            func.sum(summary.available_beds).label("beds_free"),
        )
        .where(*conditions)
        .lateral("matching")
    )


def _listing_conditions(filters: Filters) -> list[ColumnElement[bool]]:
    """What the listing itself must be: verified, for whom, its meals and amenities, and where."""
    listing = SearchListing
    conditions: list[ColumnElement[bool]] = []
    if filters.verified_only:
        conditions.append(listing.verified.is_(True))
    if filters.gender is not None:
        conditions.append(listing.gender_policy == filters.gender)
    if filters.meals is not None:
        conditions.append(listing.meals == filters.meals)
    if filters.amenities:
        conditions.append(listing.amenities.contains(list(filters.amenities)))
    if filters.campus is not None:
        conditions.append(
            func.ST_DWithin(
                listing.display_location, postgis.geography(filters.campus), filters.radius_m
            )
        )
    if filters.locality_id is not None:
        conditions.append(listing.locality_id == filters.locality_id)
    if filters.bbox is not None:
        box = filters.bbox
        envelope = func.geography(
            func.ST_MakeEnvelope(box.west, box.south, box.east, box.north, 4326)
        )
        conditions.append(func.ST_Intersects(listing.display_location, envelope))
    return conditions


def _hit(row: tuple[Any, ...]) -> Hit:
    (property_id, public_id, slug, name, locality_slug, locality_name, lat, lng) = row[:8]
    gender, meals, verified, licensed, media_ids, low, high, beds, metres, value = row[8:]
    return Hit(
        property_id=property_id,
        public_id=public_id,
        slug=slug,
        name=name,
        locality_slug=locality_slug,
        locality_name=locality_name,
        display=Point(lat=lat, lng=lng),
        gender_policy=gender,
        meals=meals,
        verified=verified,
        licensed=licensed,
        media_ids=tuple(media_ids),
        min_rent=low,
        max_rent=high,
        beds_free=int(beds),
        distance_m=metres,
        key=value.isoformat() if isinstance(value, datetime) else value,
    )
