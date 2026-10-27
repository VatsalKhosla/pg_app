"""Search routes (ARCHITECTURE §10.1, §15; ADR 0028): live listings, for anyone."""

from datetime import date, timedelta
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.clock import ClockDep
from app.core.db import DbSession
from app.core.geometry import Bounds
from app.core.money import Paise
from app.core.ratelimit import RateLimit, rate_limited
from app.modules.catalog.domain.listing import GenderPolicy, Meals
from app.modules.catalog.schemas import LatLng, ListingLocality, PublicMedia, Rendition
from app.modules.search.domain.query import SearchRequest, beds_free
from app.modules.search.schemas import SearchCard, SearchPage, SearchQuery, StationNearby
from app.modules.search.service import Card, Search

router = APIRouter(prefix="/v1", tags=["search"])

# Generous, since many students share an address (college Wi-Fi, carriers' NAT); let through if
# Redis is down, as searching should never stop.
SEARCHES_PER_IP: Final = RateLimit("searches-per-ip", limit=600, window=timedelta(minutes=10))
# Results move as listings change; a little caching spares the database repeated searches.
CACHE_CONTROL: Final = "public, max-age=30"


def _request(query: SearchQuery) -> SearchRequest:
    bbox = None
    if query.bbox is not None:
        west, south, east, north = (float(part) for part in query.bbox.split(","))
        bbox = Bounds(south=south, west=west, north=north, east=east)
    month = None
    if query.move_in_month is not None:
        year, number = query.move_in_month.split("-")
        month = date(int(year), int(number), 1)
    return SearchRequest(
        campus=query.campus,
        radius_m=query.radius_m,
        locality=query.locality,
        bbox=bbox,
        month=month,
        budget_min=None if query.budget_min_paise is None else Paise(query.budget_min_paise),
        budget_max=None if query.budget_max_paise is None else Paise(query.budget_max_paise),
        gender=None if query.gender is None else query.gender.value,
        occupancy=None if query.occupancy is None else query.occupancy.value,
        meals=None if query.meals is None else query.meals.value,
        ac=query.ac,
        attached_bath=query.attached_bath,
        amenities=tuple(sorted(set(query.amenities))),
        verified_only=query.verified_only,
        available=query.available,
        text=None if query.q is None or not query.q.strip() else query.q.strip(),
        sort=query.sort,
        cursor=query.cursor,
        limit=query.limit,
    )


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
