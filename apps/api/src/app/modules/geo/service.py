"""Geo use cases (ADR 0020): what the public geo endpoints read, and loading the reference data.

Loading is idempotent: rows are matched by slug, and only rows whose values changed are written,
so loading the same data again changes nothing (and writes no audit entry). Rows the data no
longer lists are counted but left alone, since properties may refer to them; removing one is a
migration's job.
"""

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core import audit
from app.core.errors import NotFoundError
from app.core.postgis import multipolygon_wkt, point_wkt
from app.modules.geo.models import Campus, City, Locality, MetroLine, MetroStation
from app.modules.geo.reference import dump_reference_data
from app.modules.geo.repository import (
    CampusRecord,
    CampusSurroundings,
    CityRecord,
    GeoRepository,
    LocalityRecord,
    StationRecord,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.clock import Clock
    from app.modules.geo.domain.places import OsmRef
    from app.modules.geo.reference import ReferenceData


class GeoDirectory:
    """The cities, localities, campuses and metro stations people choose PGs by."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._geo = GeoRepository(db)

    async def cities(self) -> list[CityRecord]:
        async with self._db.begin():
            return await self._geo.cities()

    async def localities(self, *, city: str | None) -> list[LocalityRecord]:
        async with self._db.begin():
            return await self._geo.localities(city=city)

    async def campuses(self, *, city: str | None) -> list[CampusRecord]:
        async with self._db.begin():
            return await self._geo.campuses(city=city)

    async def campus(self, slug: str) -> CampusSurroundings:
        async with self._db.begin():
            found = await self._geo.surroundings(slug)
        if found is None:
            raise NotFoundError
        return found

    async def metro_stations(self) -> list[StationRecord]:
        async with self._db.begin():
            return await self._geo.stations()


@dataclass(frozen=True, slots=True)
class LocalityRef:
    """A locality, as another module refers to it."""

    id: int
    slug: str
    name: str


class GeoLookup:
    """Geo reads for other modules, inside the caller's transaction (it starts none)."""

    def __init__(self, db: AsyncSession) -> None:
        self._geo = GeoRepository(db)

    async def locality(self, slug: str) -> LocalityRef | None:
        found = await self._geo.locality(slug)
        return None if found is None else LocalityRef(id=found[0], slug=slug, name=found[1])


@dataclass(frozen=True, slots=True)
class Loaded:
    """What loading did to one kind of row."""

    kind: str
    rows: int
    inserted: int
    updated: int
    # Rows in the database that the data no longer lists, left alone.
    not_listed: int


@dataclass(frozen=True, slots=True)
class LoadReport:
    kinds: tuple[Loaded, ...]
    station_lines_changed: int
    # The SHA-256 of the data loaded, as places.json holds it.
    digest: str

    @property
    def changed(self) -> bool:
        return self.station_lines_changed > 0 or any(
            kind.inserted or kind.updated for kind in self.kinds
        )


def _osm(ref: OsmRef) -> dict[str, object]:
    return {"osm_type": ref.type.value, "osm_id": ref.id}


class GeoReferenceLoader:
    """Loads the reference data, in one transaction: ``python -m app.manage geo load``."""

    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._db = db
        self._clock = clock
        self._geo = GeoRepository(db)

    async def load(self, data: ReferenceData) -> LoadReport:
        async with self._db.begin():
            await self._geo.lock_for_loading()
            report = await self._load(data)
            if report.changed:
                await audit.record(
                    self._db,
                    clock=self._clock,
                    actor=audit.SYSTEM,
                    action="geo.reference_loaded",
                    entity_type="geo_reference",
                    entity_id=report.digest,
                    details={
                        "retrieved_on": data.retrieved_on.isoformat(),
                        "station_lines_changed": report.station_lines_changed,
                        **{
                            kind.kind: {"inserted": kind.inserted, "updated": kind.updated}
                            for kind in report.kinds
                        },
                    },
                )
        return report

    async def _load(self, data: ReferenceData) -> LoadReport:
        geo = self._geo
        cities = await geo.upsert(
            City,
            [
                {
                    "slug": city.slug,
                    "name": city.name,
                    "center": point_wkt(city.center.point),
                    **_osm(city.osm_ref),
                }
                for city in data.cities
            ],
            geographies={"center"},
        )
        localities = await geo.upsert(
            Locality,
            [
                {
                    "slug": locality.slug,
                    "city_id": cities.ids[locality.city],
                    "name": locality.name,
                    "center": point_wkt(locality.center.point),
                    "boundary": None
                    if locality.boundary is None
                    else multipolygon_wkt(locality.boundary.coordinates),
                    **_osm(locality.osm_ref),
                }
                for locality in data.localities
            ],
            geographies={"center", "boundary"},
        )
        campuses = await geo.upsert(
            Campus,
            [
                {
                    "slug": campus.slug,
                    "city_id": cities.ids[campus.city],
                    "name": campus.name,
                    "location": point_wkt(campus.location.point),
                    **_osm(campus.osm_ref),
                }
                for campus in data.campuses
            ],
            geographies={"location"},
        )
        lines = await geo.upsert(
            MetroLine,
            [
                {
                    "slug": line.slug,
                    "name": line.name,
                    "colour": line.colour,
                    "wikidata_id": line.wikidata,
                }
                for line in data.metro_lines
            ],
        )
        stations = await geo.upsert(
            MetroStation,
            [
                {
                    "slug": station.slug,
                    "name": station.name,
                    "location": point_wkt(station.location.point),
                    "wikidata_id": station.wikidata,
                    **_osm(station.osm_ref),
                }
                for station in data.metro_stations
            ],
            geographies={"location"},
        )
        station_lines_changed = await geo.set_station_lines(
            list(stations.ids.values()),
            {
                (stations.ids[station.slug], lines.ids[line])
                for station in data.metro_stations
                for line in station.lines
            },
        )
        kinds = []
        for kind, model, upserted in (
            ("cities", City, cities),
            ("localities", Locality, localities),
            ("campuses", Campus, campuses),
            ("metro_lines", MetroLine, lines),
            ("metro_stations", MetroStation, stations),
        ):
            kinds.append(
                Loaded(
                    kind=kind,
                    rows=len(upserted.ids),
                    inserted=upserted.inserted,
                    updated=upserted.updated,
                    not_listed=await geo.not_in(model, upserted.ids.keys()),
                )
            )
        return LoadReport(
            kinds=tuple(kinds),
            station_lines_changed=station_lines_changed,
            digest=hashlib.sha256(dump_reference_data(data).encode()).hexdigest(),
        )
