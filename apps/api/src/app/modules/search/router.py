"""Search routes (ARCHITECTURE §10.1, §10.2, §15; ADR 0028, 0029, 0032): live listings, the
map's pins, where the PGs are and every live one for the sitemap, for anyone."""

from datetime import date, timedelta
from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.clock import ClockDep
from app.core.db import DbSession
from app.core.geometry import Bounds
from app.core.money import Paise
from app.core.ratelimit import RateLimit, rate_limited
from app.modules.catalog.domain.listing import GenderPolicy, Meals
from app.modules.catalog.schemas import LatLng, ListingLocality, PublicMedia, Rendition
from app.modules.search.cache import PinCache
from app.modules.search.domain.query import SearchRequest, beds_free
from app.modules.search.schemas import (
    FilterParams,
    MapPins,
    PinsQuery,
    SearchCard,
    SearchPage,
    SearchPlace,
    SearchPlaces,
    SearchQuery,
    SitemapListing,
    SitemapPage,
    SitemapQuery,
    StationNearby,
)
from app.modules.search.service import Card, Pins, Places, Search, Sitemap

router = APIRouter(prefix="/v1", tags=["search"])

# Generous, since many students share an address (college Wi-Fi, carriers' NAT); let through if
# Redis is down, as searching should never stop.
SEARCHES_PER_IP: Final = RateLimit("searches-per-ip", limit=600, window=timedelta(minutes=10))
# Results move as listings change; a little caching spares the database repeated searches.
CACHE_CONTROL: Final = "public, max-age=30"
# The map asks again with every pan: a generous limit, and pins kept a minute (ADR 0029).
PINS_PER_IP: Final = RateLimit("map-pins-per-ip", limit=1_200, window=timedelta(minutes=10))
PINS_CACHE_CONTROL: Final = "public, max-age=60"
# Where the PGs are moves only as listings do; the web app is told when they do (ADR 0032).
PLACES_CACHE_CONTROL: Final = "public, max-age=300"


def _bounds(bbox: str) -> Bounds:
    west, south, east, north = (float(part) for part in bbox.split(","))
    return Bounds(south=south, west=west, north=north, east=east)


def _filters(query: FilterParams) -> dict[str, Any]:
    """The filters search and the map share, as the domain has them."""
    month = None
    if query.move_in_month is not None:
        year, number = query.move_in_month.split("-")
        month = date(int(year), int(number), 1)
    return {
        "month": month,
        "budget_min": None if query.budget_min_paise is None else Paise(query.budget_min_paise),
        "budget_max": None if query.budget_max_paise is None else Paise(query.budget_max_paise),
        "gender": None if query.gender is None else query.gender.value,
        "occupancy": None if query.occupancy is None else query.occupancy.value,
        "meals": None if query.meals is None else query.meals.value,
        "ac": query.ac,
        "attached_bath": query.attached_bath,
        "amenities": tuple(sorted(set(query.amenities))),
        "verified_only": query.verified_only,
        "available": query.available,
        "text": None if query.q is None or not query.q.strip() else query.q.strip(),
    }


def _request(query: SearchQuery) -> SearchRequest:
    return SearchRequest(
        campus=query.campus,
        radius_m=query.radius_m,
        locality=query.locality,
        bbox=None if query.bbox is None else _bounds(query.bbox),
        sort=query.sort,
        cursor=query.cursor,
        limit=query.limit,
        **_filters(query),
    )


def _etags(header: str | None) -> set[str]:
    """The ETags an If-None-Match header names, weak ones as strong."""
    if header is None:
        return set()
    return {tag.strip().removeprefix("W/") for tag in header.split(",")}


def _card(card: Card) -> SearchCard:
    hit, station, cover = card.hit, card.station, card.cover
    return SearchCard(
        id=hit.public_id,
        slug=hit.slug,
        name=hit.name,
        locality=ListingLocality(slug=hit.locality_slug, name=hit.locality_name),
        display_location=LatLng(lat=hit.display.lat, lng=hit.display.lng),
        distance_m=None if hit.distance_m is None else round(hit.distance_m),
        nearest_station=None
        if station is None
        else StationNearby(
            slug=station.slug, name=station.name, distance_m=round(station.distance_m)
        ),
        min_rent_paise=hit.min_rent,
        max_rent_paise=hit.max_rent,
        gender_policy=GenderPolicy(hit.gender_policy),
        meals=Meals(hit.meals),
        verified=hit.verified,
        licensed=hit.licensed,
        cover=None
        if cover is None
        else PublicMedia(
            id=cover.public_id,
            content_type=cover.content_type,
            verified_capture=cover.verified_capture,
            renditions=[
                Rendition(
                    name=rendition.name,
                    content_type=rendition.content_type,
                    url=rendition.url,
                    width=rendition.width,
                    height=rendition.height,
                )
                for rendition in cover.renditions
            ],
        ),
        beds_free=beds_free(hit.beds_free),
    )


@router.get(
    "/search/properties",
    summary="Search live PGs",
    dependencies=[Depends(rate_limited(SEARCHES_PER_IP))],
)
async def search_properties(
    query: Annotated[SearchQuery, Query()],
    request: Request,
    response: Response,
    db: DbSession,
    clock: ClockDep,
) -> SearchPage:
    """Around one place at most (a campus within a radius, a locality or a map area), for a
    move-in month, by budget and what the PG and its rooms offer, sorted and a page at a time.
    Distances are from display points. 422 SEARCH_INVALID for a search that can't be answered."""
    state = request.app.state
    results = await Search(db, clock, buckets=state.media_buckets, flags=state.flags).search(
        _request(query)
    )
    response.headers["Cache-Control"] = CACHE_CONTROL
    return SearchPage(
        items=[_card(card) for card in results.cards],
        next_cursor=results.next_cursor,
        month=results.month,
    )


@router.get(
    "/map/pins",
    summary="Pins for the map's area",
    response_model=MapPins,
    responses={304: {"description": "Not modified: the pins with that ETag are still current."}},
    dependencies=[Depends(rate_limited(PINS_PER_IP))],
)
async def map_pins(
    query: Annotated[PinsQuery, Query()], request: Request, db: DbSession, clock: ClockDep
) -> Response:
    """Every live listing in the area that matches the filters, as a pin at its display point,
    2,000 at most (``truncated`` says there were more: zoom in). Cached for a minute by the
    area snapped to the zoom's grid, the zoom and the filters, with an ETag."""
    state = request.app.state
    found = await Pins(db, clock, flags=state.flags, cache=PinCache(state.redis)).pins(
        SearchRequest(bbox=_bounds(query.bbox), **_filters(query)), zoom=query.zoom
    )
    etag = f'"{found.etag}"'
    headers = {"ETag": etag, "Cache-Control": PINS_CACHE_CONTROL}
    if {etag, "*"} & _etags(request.headers.get("if-none-match")):
        return Response(status_code=304, headers=headers)
    return Response(content=found.body, media_type="application/json", headers=headers)


@router.get(
    "/search/places",
    summary="Where the live PGs are",
    dependencies=[Depends(rate_limited(SEARCHES_PER_IP))],
)
async def search_places(response: Response, db: DbSession, clock: ClockDep) -> SearchPlaces:
    """Each campus with verified live PGs within ``radiusM`` and each locality with some, most
    first: how many, and what their rooms come to this month. For landing pages and links."""
    found = await Places(db, clock).places()
    response.headers["Cache-Control"] = PLACES_CACHE_CONTROL
    return SearchPlaces(
        items=[
            SearchPlace(
                kind=place.kind,
                slug=place.row.slug,
                name=place.row.name,
                listings=place.row.listings,
                min_rent_paise=place.row.min_rent,
                max_rent_paise=place.row.max_rent,
            )
            for place in found.places
        ],
        month=found.month,
        radius_m=found.radius_m,
    )


@router.get(
    "/search/sitemap",
    summary="Every live PG, for the sitemap",
    dependencies=[Depends(rate_limited(SEARCHES_PER_IP))],
)
async def search_sitemap(
    query: Annotated[SitemapQuery, Query()], request: Request, response: Response, db: DbSession
) -> SitemapPage:
    """Every listing whose page anyone may see, in a stable order, a page at a time, with when
    it last changed. 422 SEARCH_INVALID for a cursor this didn't give."""
    found = await Sitemap(db, flags=request.app.state.flags).page(query.cursor, limit=query.limit)
    response.headers["Cache-Control"] = PLACES_CACHE_CONTROL
    return SitemapPage(
        items=[SitemapListing(slug=row.slug, changed_at=row.changed_at) for row in found.rows],
        next_cursor=found.next_cursor,
    )
