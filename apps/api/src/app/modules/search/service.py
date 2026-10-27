"""Search's use cases (steps 3.1 and 3.2; ADR 0027, 0028).

Keeping the index: after each catalog event about a listing (its rents, rooms or beds, or its own
details), and every night, the listing's search entry and price summaries are worked out again.
These run inside a job's transaction (they start none): the worker commits them with the job's
"done" mark.

Searching: one page of live listings, filtered, sorted and cut by a cursor, with the distance from
the chosen campus and the nearest metro station measured from display points (ADR 0021), and
each card's cover. A fixed number of queries, however many listings match.

The map's pins: every live listing in an area that matches the same filters, at most 2,000,
cached for a minute (step 3.3).
"""

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import structlog

from app.core.calendar import india_date
from app.core.flags import Flag
from app.core.outbox import enqueue
from app.modules.catalog.domain.listing import GenderPolicy
from app.modules.catalog.service import CatalogLookup
from app.modules.geo.service import GeoLookup
from app.modules.media.domain.assets import AssetStatus, Moderation
from app.modules.media.service import MediaLookup
from app.modules.search.cache import Cached
from app.modules.search.domain.pins import PIN_CAP, cache_key, snapped
from app.modules.search.domain.query import (
    Cursor,
    SearchRequest,
    beds_free,
    decode_cursor,
    encode_cursor,
    order_for,
    request_problems,
)
from app.modules.search.domain.summaries import CategoryRent, months_from, summarise
from app.modules.search.errors import SearchInvalidError
from app.modules.search.repository import Filters, Hit, SearchRepository, SummaryRepository
from app.modules.search.schemas import MapPin, MapPins

if TYPE_CHECKING:
    from datetime import date

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.clock import Clock
    from app.core.flags import FlagReader
    from app.core.geometry import Bounds, Point
    from app.modules.geo.service import PlaceNear
    from app.modules.media.service import Buckets, MediaRef
    from app.modules.search.cache import PinCache

REFRESH: Final = "search.refresh_listing"
REFRESH_ALL: Final = "search.refresh_all"
# Listings read per query by the nightly fan-out.
_PAGE: Final = 500

logger = structlog.stdlib.get_logger(__name__)


class SearchIndex:
    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._db = db
        self._clock = clock
        self._catalog = CatalogLookup(db)
        self._listings = SearchRepository(db)
        self._summaries = SummaryRepository(db)

    async def refresh(self, property_id: int) -> None:
        """Work out one listing's search entry and price summaries again, from the catalog now."""
        now = self._clock.now()
        entry = await self._catalog.search_entry(property_id)
        if entry is None:
            await self._listings.remove(property_id)
        else:
            await self._listings.put(property_id, entry, refreshed_at=now)
        rents = await self._catalog.rents(property_id)
        summaries = summarise(
            [
                CategoryRent(
                    category_id=rent.category_id,
                    base_rent=rent.base_rent,
                    active_beds=rent.active_beds,
                    occupancy=rent.occupancy.value,
                    ac=rent.ac,
                    attached_bath=rent.attached_bath,
                )
                for rent in rents
            ],
            months_from(india_date(now)),
        )
        await self._summaries.replace(property_id, summaries, computed_at=now)

    async def refresh_all(self) -> int:
        """Ask for every listing's refresh, one job each; a second run the same day adds
        nothing. How many jobs it added."""
        today = india_date(self._clock.now()).isoformat()
        added, after = 0, None
        while ids := await self._catalog.property_ids(after=after, limit=_PAGE):
            for property_id in ids:
                added += await enqueue(
                    self._db,
                    REFRESH,
                    {"property_id": property_id},
                    clock=self._clock,
                    dedupe_key=f"{REFRESH}:{property_id}:{today}",
                )
            after = ids[-1]
        logger.info("search refresh queued for every listing", jobs=added)
        return added


@dataclass(frozen=True, slots=True)
class Card:
    hit: Hit
    station: PlaceNear | None
    cover: MediaRef | None


@dataclass(frozen=True, slots=True)
class Results:
    cards: list[Card]
    next_cursor: str | None
    # The month the prices are for.
    month: date


def _cover(hit: Hit, media: dict[int, MediaRef]) -> MediaRef | None:
    """The first of the listing's photos that's ready and approved, with public links."""
    for media_id in hit.media_ids:
        ref = media.get(media_id)
        if (
            ref is not None
            and ref.status is AssetStatus.READY
            and ref.moderation is Moderation.APPROVED
            and ref.renditions
        ):
            return ref
    return None


class Search:
    def __init__(
        self, db: AsyncSession, clock: Clock, *, buckets: Buckets, flags: FlagReader
    ) -> None:
        self._db = db
        self._clock = clock
        self._flags = flags
        self._geo = GeoLookup(db)
        # Without storage, so private files can't be signed for the public.
        self._media = MediaLookup(db, buckets)
        self._search = SearchRepository(db)

    async def search(self, request: SearchRequest) -> Results:
        months = months_from(india_date(self._clock.now()))
        problems = request_problems(request, months=months)
        order = order_for(
            request.sort, has_text=request.text is not None, has_campus=request.campus is not None
        )
        cursor = None
        if request.cursor is not None:
            cursor = decode_cursor(request.cursor)
            if cursor is None:
                problems.append("that isn't a cursor this search gave")
            elif cursor.order is not order:
                problems.append("that cursor is from a search sorted another way")
        if problems:
            raise SearchInvalidError(problems)
        # Only verified PGs show while verified_only is on, whatever the search asks.
        verified_only = request.verified_only or await self._flags.is_enabled(Flag.VERIFIED_ONLY)
        month = request.month or months[0]
        async with self._db.begin():
            filters = await self._filters(request, month=month, verified_only=verified_only)
            hits = await self._search.search(
                filters, order=order, cursor=cursor, limit=request.limit
            )
            page = hits[: request.limit]
            stations = await self._geo.nearest_stations([hit.display for hit in page])
            media = await self._media.by_id(
                {media_id for hit in page for media_id in hit.media_ids}
            )
        next_cursor = (
            encode_cursor(Cursor(order=order, key=page[-1].key, after=page[-1].public_id))
            if len(hits) > request.limit
            else None
        )
        return Results(
            cards=[
                Card(hit=hit, station=station, cover=_cover(hit, media))
                for hit, station in zip(page, stations, strict=True)
            ],
            next_cursor=next_cursor,
            month=month,
        )

    async def _filters(
        self, request: SearchRequest, *, month: date, verified_only: bool
    ) -> Filters:
        campus = None
        if request.campus is not None:
            found = await self._geo.campus(request.campus)
            if found is None:
                raise SearchInvalidError(["no campus has that slug"])
            campus = found.location
        locality_id = None
        if request.locality is not None:
            locality = await self._geo.locality(request.locality)
            if locality is None:
                raise SearchInvalidError(["no locality has that slug"])
            locality_id = locality.id
        return _filters(
            request,
            month=month,
            verified_only=verified_only,
            campus=campus,
            locality_id=locality_id,
            bbox=request.bbox,
        )


def _filters(
    request: SearchRequest,
    *,
    month: date,
    verified_only: bool,
    bbox: Bounds | None,
    campus: Point | None = None,
    locality_id: int | None = None,
) -> Filters:
    return Filters(
        month=month,
        campus=campus,
        radius_m=request.radius_m,
        locality_id=locality_id,
        bbox=bbox,
        budget_min=request.budget_min,
        budget_max=request.budget_max,
        gender=request.gender,
        occupancy=request.occupancy,
        meals=request.meals,
        ac=request.ac,
        attached_bath=request.attached_bath,
        amenities=request.amenities,
        verified_only=verified_only,
        available=request.available,
        text=request.text,
    )


class Pins:
    """The map's pins (step 3.3, ADR 0029): every live listing in the area that matches, as
    the API answers, cached for a minute by the snapped area, the zoom and the filters."""

    def __init__(
        self, db: AsyncSession, clock: Clock, *, flags: FlagReader, cache: PinCache
    ) -> None:
        self._db = db
        self._clock = clock
        self._flags = flags
        self._cache = cache
        self._search = SearchRepository(db)

    async def pins(self, request: SearchRequest, *, zoom: int) -> Cached:
        """The answer, as JSON, with its ETag: from the cache when it's there."""
        months = months_from(india_date(self._clock.now()))
        problems = request_problems(request, months=months)
        if request.bbox is None:  # pragma: no cover - the API asks for one
            problems.append("pins need a map area")
        if problems:
            raise SearchInvalidError(problems)
        assert request.bbox is not None  # noqa: S101 - checked above
        verified_only = request.verified_only or await self._flags.is_enabled(Flag.VERIFIED_ONLY)
        month = request.month or months[0]
        area = snapped(request.bbox, zoom)
        key = cache_key(request, area=area, zoom=zoom, month=month, verified_only=verified_only)
        cached = await self._cache.get(key)
        if cached is not None:
            return cached
        async with self._db.begin():
            rows = await self._search.pins(
                _filters(request, month=month, verified_only=verified_only, bbox=area),
                limit=PIN_CAP + 1,
            )
        body = (
            MapPins(
                pins=[
                    MapPin(
                        id=row.public_id,
                        slug=row.slug,
                        lat=row.display.lat,
                        lng=row.display.lng,
                        min_rent_paise=row.min_rent,
                        max_rent_paise=row.max_rent,
                        gender_policy=GenderPolicy(row.gender_policy),
                        verified=row.verified,
                        beds_free=beds_free(row.beds_free),
                    )
                    for row in rows[:PIN_CAP]
                ],
                truncated=len(rows) > PIN_CAP,
                month=month,
            )
            .model_dump_json(by_alias=True)
            .encode()
        )
        cached = Cached(etag=hashlib.sha256(body).hexdigest()[:32], body=body)
        await self._cache.put(key, cached)
        return cached
