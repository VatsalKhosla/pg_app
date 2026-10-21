"""Geo routes (ARCHITECTURE §15): the public reference data people choose PGs by.

Anyone may read it, signed in or not. It changes only when the reference data is loaded, so
browsers and CDNs may keep a response for an hour.
"""

from typing import Annotated, Final

from fastapi import APIRouter, Path, Query, Response

from app.core.db import DbSession
from app.core.geometry import Point
from app.modules.geo.domain.places import SLUG_MAX_LENGTH, SLUG_PATTERN
from app.modules.geo.repository import (
    CampusRecord,
    LocalityRecord,
    NearbyLocality,
    NearbyStation,
    StationRecord,
)
from app.modules.geo.schemas import (
    CampusDetail,
    CampusInfo,
    CampusList,
    CityInfo,
    CityList,
    LocalityDistance,
    LocalityInfo,
    LocalityList,
    Location,
    MetroLineInfo,
    MetroStationInfo,
    MetroStationList,
    StationDistance,
)
from app.modules.geo.service import GeoDirectory

router = APIRouter(prefix="/v1", tags=["geo"])

CACHE_CONTROL: Final = "public, max-age=3600"
_SLUG: Final = f"^{SLUG_PATTERN.pattern}$"

CityFilter = Annotated[
    str | None,
    Query(pattern=_SLUG, max_length=SLUG_MAX_LENGTH, description="Only this city's (its slug)"),
]


def _location(point: Point) -> Location:
    return Location(lat=point.lat, lng=point.lng)


def _station(station: StationRecord) -> MetroStationInfo:
    return MetroStationInfo(
        slug=station.slug,
        name=station.name,
        location=_location(station.location),
        lines=[
            MetroLineInfo(slug=line.slug, name=line.name, colour=line.colour)
            for line in station.lines
        ],
    )


def _nearby_station(nearby: NearbyStation) -> StationDistance:
    return StationDistance(station=_station(nearby.station), distance_m=round(nearby.distance_m))


def _locality(locality: LocalityRecord) -> LocalityInfo:
    return LocalityInfo(
        slug=locality.slug,
        city=locality.city,
        name=locality.name,
        center=_location(locality.center),
    )


def _nearby_locality(nearby: NearbyLocality) -> LocalityDistance:
    return LocalityDistance(
        locality=_locality(nearby.locality), distance_m=round(nearby.distance_m)
    )


def _campus(campus: CampusRecord) -> CampusInfo:
    return CampusInfo(
        slug=campus.slug,
        city=campus.city,
        name=campus.name,
        location=_location(campus.location),
        nearest_station=None
        if campus.nearest_station is None
        else _nearby_station(campus.nearest_station),
    )


@router.get("/cities", summary="Cities")
async def cities(response: Response, db: DbSession) -> CityList:
    response.headers["Cache-Control"] = CACHE_CONTROL
    return CityList(
        items=[
            CityInfo(slug=city.slug, name=city.name, center=_location(city.center))
            for city in await GeoDirectory(db).cities()
        ]
    )


@router.get("/localities", summary="Localities, by name")
async def localities(response: Response, db: DbSession, city: CityFilter = None) -> LocalityList:
    """Where PGs are, with each one's centre; a city's only, if given."""
    response.headers["Cache-Control"] = CACHE_CONTROL
    found = await GeoDirectory(db).localities(city=city)
    return LocalityList(items=[_locality(locality) for locality in found])


@router.get("/campuses", summary="Campuses, by name, with the nearest metro station")
async def campuses(response: Response, db: DbSession, city: CityFilter = None) -> CampusList:
    response.headers["Cache-Control"] = CACHE_CONTROL
    found = await GeoDirectory(db).campuses(city=city)
    return CampusList(items=[_campus(campus) for campus in found])


@router.get("/campuses/{slug}", summary="A campus, with the metro stations and localities near it")
async def campus(
    slug: Annotated[str, Path(pattern=_SLUG, max_length=SLUG_MAX_LENGTH)],
    response: Response,
    db: DbSession,
) -> CampusDetail:
    """The three closest metro stations, and the localities within 2 km, nearest first."""
    found = await GeoDirectory(db).campus(slug)
    response.headers["Cache-Control"] = CACHE_CONTROL
    info = _campus(found.campus)
    return CampusDetail(
        slug=info.slug,
        city=info.city,
        name=info.name,
        location=info.location,
        nearest_station=info.nearest_station,
        stations=[_nearby_station(nearby) for nearby in found.stations],
        localities=[_nearby_locality(nearby) for nearby in found.localities],
    )


@router.get("/metro-stations", summary="Metro stations, by name, with their lines")
async def metro_stations(response: Response, db: DbSession) -> MetroStationList:
    response.headers["Cache-Control"] = CACHE_CONTROL
    found = await GeoDirectory(db).metro_stations()
    return MetroStationList(items=[_station(station) for station in found])
