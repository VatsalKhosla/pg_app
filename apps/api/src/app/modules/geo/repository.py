"""Geo queries (ARCHITECTURE §6): loading the reference data, and the lists and distances the API
serves. Distances are PostGIS's, in metres on the ellipsoid; nearest-first orderings use the GiST
indexes (``<->``)."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    ColumnElement,
    Float,
    Integer,
    and_,
    column,
    delete,
    func,
    literal_column,
    or_,
    select,
    true,
    tuple_,
    values,
)
from sqlalchemy.dialects.postgresql import insert

from app.core import postgis
from app.core.geometry import Point
from app.modules.geo.domain.places import NEARBY_RADIUS_M, NEAREST_STATIONS
from app.modules.geo.models import (
    Campus,
    City,
    Locality,
    MetroLine,
    MetroStation,
    MetroStationLine,
    ReferenceRow,
)

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession


def _by_name(model: type[ReferenceRow]) -> tuple[ColumnElement[str], ColumnElement[str]]:
    """Name order that is the same in every environment, whatever the database's locale: by
    lower-cased name, byte by byte, then slug."""
    return func.lower(model.name).collate("C"), model.slug.collate("C")


@dataclass(frozen=True, slots=True)
class Upserted:
    """What an upsert did: the id of every row it was given, by slug, and what changed."""

    ids: dict[str, int]
    inserted: int
    updated: int


@dataclass(frozen=True, slots=True)
class CityRecord:
    slug: str
    name: str
    center: Point


@dataclass(frozen=True, slots=True)
class LocalityRecord:
    slug: str
    city: str
    name: str
    center: Point


@dataclass(frozen=True, slots=True)
class LineRecord:
    slug: str
    name: str
    colour: str


@dataclass(frozen=True, slots=True)
class StationRecord:
    slug: str
    name: str
    location: Point
    lines: tuple[LineRecord, ...]


@dataclass(frozen=True, slots=True)
class NearbyStation:
    station: StationRecord
    distance_m: float


@dataclass(frozen=True, slots=True)
class NearbyLocality:
    locality: LocalityRecord
    # From the campus to the locality's boundary (0 inside it), or to its centre if it has none.
    distance_m: float


@dataclass(frozen=True, slots=True)
class CampusRecord:
    slug: str
    city: str
    name: str
    location: Point
    nearest_station: NearbyStation | None


@dataclass(frozen=True, slots=True)
class CampusSurroundings:
    campus: CampusRecord
    stations: list[NearbyStation]
    localities: list[NearbyLocality]


class GeoRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # Loading.

    async def lock_for_loading(self) -> None:
        """Until the transaction ends, no other load runs (two deploys starting at once)."""
        await self._db.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended("geo:reference", 0)))
        )

    async def upsert(
        self,
        model: type[ReferenceRow],
        rows: Sequence[Mapping[str, object]],
        *,
        geographies: Collection[str] = (),
    ) -> Upserted:
        """Insert or update rows by slug, touching only rows whose values changed. Geography
        columns compare as WKB, which is exact."""
        if not rows:
            return Upserted(ids={}, inserted=0, updated=0)
        statement = insert(model).values(list(rows))
        fields = [name for name in rows[0] if name != "slug"]

        def differs(name: str) -> ColumnElement[bool]:
            current: ColumnElement[object] = getattr(model, name)
            given = statement.excluded[name]
            if name in geographies:
                return func.ST_AsBinary(current).is_distinct_from(func.ST_AsBinary(given))
            return current.is_distinct_from(given)

        changed = await self._db.execute(
            statement.on_conflict_do_update(
                index_elements=["slug"],
                set_={name: statement.excluded[name] for name in fields}
                | {"updated_at": func.now()},
                where=or_(*(differs(name) for name in fields)),
            ).returning(literal_column("xmax = 0", Boolean))
        )
        fresh = [inserted for (inserted,) in changed]
        slugs = [str(row["slug"]) for row in rows]
        found = await self._db.execute(select(model.slug, model.id).where(model.slug.in_(slugs)))
        return Upserted(
            ids={row.slug: row.id for row in found},
            inserted=sum(fresh),
            updated=len(fresh) - sum(fresh),
        )

    async def not_in(self, model: type[ReferenceRow], slugs: Collection[str]) -> int:
        """How many rows the reference data no longer lists (left alone: rows may refer to them)."""
        query = select(func.count()).select_from(model).where(model.slug.not_in(slugs))
        return await self._db.scalar(query) or 0

    async def set_station_lines(
        self, station_ids: Collection[int], wanted: set[tuple[int, int]]
    ) -> int:
        """Make the stations' lines exactly ``wanted`` (station id, line id): the changes made."""
        existing = {
            (station_id, line_id)
            for station_id, line_id in await self._db.execute(
                select(MetroStationLine.station_id, MetroStationLine.line_id).where(
                    MetroStationLine.station_id.in_(station_ids)
                )
            )
        }
        added, dropped = sorted(wanted - existing), sorted(existing - wanted)
        if added:
            await self._db.execute(
                insert(MetroStationLine).values(
                    [{"station_id": station, "line_id": line} for station, line in added]
                )
            )
        if dropped:
            pair = tuple_(MetroStationLine.station_id, MetroStationLine.line_id)
            await self._db.execute(delete(MetroStationLine).where(pair.in_(dropped)))
        return len(added) + len(dropped)

    # Reading.

    async def locality(self, slug: str) -> tuple[int, str] | None:
        """A locality's internal id and name."""
        found = (
            await self._db.execute(select(Locality.id, Locality.name).where(Locality.slug == slug))
        ).one_or_none()
        return None if found is None else (found.id, found.name)

    async def campus_point(self, slug: str) -> tuple[int, str, Point] | None:
        """A campus's internal id, name and location."""
        found = (
            await self._db.execute(
                select(
                    Campus.id,
                    Campus.name,
                    postgis.lat(Campus.location),
                    postgis.lng(Campus.location),
                ).where(Campus.slug == slug)
            )
        ).one_or_none()
        if found is None:
            return None
        campus_id, name, lat, lng = found
        return campus_id, name, Point(lat=lat, lng=lng)

    async def nearest_station_to_each(
        self, points: Sequence[Point]
    ) -> list[tuple[str, str, float] | None]:
        """The metro station nearest each point: its slug, name and distance in metres. One query
        however many points."""
        if not points:
            return []
        given = values(
            column("position", Integer), column("lng", Float), column("lat", Float), name="given"
        ).data([(position, point.lng, point.lat) for position, point in enumerate(points)])
        here = func.geography(func.ST_SetSRID(func.ST_MakePoint(given.c.lng, given.c.lat), 4326))
        nearest = (
            select(
                MetroStation.slug.label("slug"),
                MetroStation.name.label("name"),
                postgis.distance(MetroStation.location, here).label("distance"),
            )
            .order_by(MetroStation.location.op("<->")(here))
            .limit(1)
            .lateral("nearest")
        )
        rows = await self._db.execute(
            select(given.c.position, nearest.c.slug, nearest.c.name, nearest.c.distance)
            .select_from(given)
            .join(nearest, true())
        )
        found = {position: (slug, name, metres) for position, slug, name, metres in rows}
        return [found.get(position) for position in range(len(points))]

    async def localities_by_id(self, ids: Collection[int]) -> dict[int, tuple[str, str]]:
        """Localities' slugs and names, by internal id."""
        if not ids:
            return {}
        rows = await self._db.execute(
            select(Locality.id, Locality.slug, Locality.name).where(Locality.id.in_(ids))
        )
        return {row.id: (row.slug, row.name) for row in rows}

    async def cities(self) -> list[CityRecord]:
        rows = await self._db.execute(
            select(
                City.slug, City.name, postgis.lat(City.center), postgis.lng(City.center)
            ).order_by(*_by_name(City))
        )
        return [
            CityRecord(slug=slug, name=name, center=Point(lat=lat, lng=lng))
            for slug, name, lat, lng in rows
        ]

    async def localities(self, *, city: str | None = None) -> list[LocalityRecord]:
        query = (
            select(
                Locality.slug,
                City.slug,
                Locality.name,
                postgis.lat(Locality.center),
                postgis.lng(Locality.center),
            )
            .join(City, City.id == Locality.city_id)
            .order_by(*_by_name(Locality))
        )
        if city is not None:
            query = query.where(City.slug == city)
        return [
            LocalityRecord(slug=slug, city=city_slug, name=name, center=Point(lat=lat, lng=lng))
            for slug, city_slug, name, lat, lng in await self._db.execute(query)
        ]

    async def stations(self) -> list[StationRecord]:
        rows = list(
            await self._db.execute(
                select(
                    MetroStation.id,
                    MetroStation.slug,
                    MetroStation.name,
                    postgis.lat(MetroStation.location),
                    postgis.lng(MetroStation.location),
                ).order_by(*_by_name(MetroStation))
            )
        )
        lines = await self._lines([row_id for row_id, *_ in rows])
        return [
            StationRecord(
                slug=slug,
                name=name,
                location=Point(lat=lat, lng=lng),
                lines=lines.get(row_id, ()),
            )
            for row_id, slug, name, lat, lng in rows
        ]

    async def campuses(self, *, city: str | None = None) -> list[CampusRecord]:
        """Every campus (in one city, if given) with its nearest metro station: two queries,
        however many campuses."""
        nearest = (
            select(
                MetroStation.id.label("id"),
                MetroStation.slug.label("slug"),
                MetroStation.name.label("name"),
                postgis.lat(MetroStation.location).label("lat"),
                postgis.lng(MetroStation.location).label("lng"),
                postgis.distance(MetroStation.location, Campus.location).label("distance"),
            )
            .order_by(MetroStation.location.op("<->")(Campus.location))
            .limit(1)
            .lateral("nearest")
        )
        query = (
            select(
                Campus.slug,
                City.slug,
                Campus.name,
                postgis.lat(Campus.location),
                postgis.lng(Campus.location),
                nearest.c.id,
                nearest.c.slug,
                nearest.c.name,
                nearest.c.lat,
                nearest.c.lng,
                nearest.c.distance,
            )
            .join(City, City.id == Campus.city_id)
            .outerjoin(nearest, true())
            .order_by(*_by_name(Campus))
        )
        if city is not None:
            query = query.where(City.slug == city)
        rows = list(await self._db.execute(query))
        lines = await self._lines([row[5] for row in rows if row[5] is not None])
        campuses = []
        for slug, city_slug, name, lat, lng, station_id, *station in rows:
            nearest_station = None
            if station_id is not None:
                station_slug, station_name, station_lat, station_lng, metres = station
                nearest_station = NearbyStation(
                    station=StationRecord(
                        slug=station_slug,
                        name=station_name,
                        location=Point(lat=station_lat, lng=station_lng),
                        lines=lines.get(station_id, ()),
                    ),
                    distance_m=metres,
                )
            campuses.append(
                CampusRecord(
                    slug=slug,
                    city=city_slug,
                    name=name,
                    location=Point(lat=lat, lng=lng),
                    nearest_station=nearest_station,
                )
            )
        return campuses

    async def surroundings(self, slug: str) -> CampusSurroundings | None:
        """A campus, its nearest metro stations and the localities within reach of it."""
        found = (
            await self._db.execute(
                select(
                    Campus.id,
                    City.slug,
                    Campus.name,
                    postgis.lat(Campus.location),
                    postgis.lng(Campus.location),
                )
                .join(City, City.id == Campus.city_id)
                .where(Campus.slug == slug)
            )
        ).one_or_none()
        if found is None:
            return None
        campus_id, city_slug, name, lat, lng = found
        here = select(Campus.location).where(Campus.id == campus_id).scalar_subquery()

        stations = list(
            await self._db.execute(
                select(
                    MetroStation.id,
                    MetroStation.slug,
                    MetroStation.name,
                    postgis.lat(MetroStation.location),
                    postgis.lng(MetroStation.location),
                    postgis.distance(MetroStation.location, here),
                )
                .order_by(MetroStation.location.op("<->")(here))
                .limit(NEAREST_STATIONS)
            )
        )
        lines = await self._lines([row[0] for row in stations])
        nearby_stations = [
            NearbyStation(
                station=StationRecord(
                    slug=station_slug,
                    name=station_name,
                    location=Point(lat=station_lat, lng=station_lng),
                    lines=lines.get(station_id, ()),
                ),
                distance_m=metres,
            )
            for station_id, station_slug, station_name, station_lat, station_lng, metres in (
                stations
            )
        ]

        outline = func.coalesce(Locality.boundary, Locality.center)
        within = or_(
            func.ST_DWithin(Locality.boundary, here, NEARBY_RADIUS_M),
            and_(
                Locality.boundary.is_(None),
                func.ST_DWithin(Locality.center, here, NEARBY_RADIUS_M),
            ),
        )
        to_outline = postgis.distance(outline, here)
        localities = [
            NearbyLocality(
                locality=LocalityRecord(
                    slug=locality_slug,
                    city=locality_city,
                    name=locality_name,
                    center=Point(lat=locality_lat, lng=locality_lng),
                ),
                distance_m=metres,
            )
            for locality_slug, locality_city, locality_name, locality_lat, locality_lng, metres in (
                await self._db.execute(
                    select(
                        Locality.slug,
                        City.slug,
                        Locality.name,
                        postgis.lat(Locality.center),
                        postgis.lng(Locality.center),
                        to_outline,
                    )
                    .join(City, City.id == Locality.city_id)
                    .where(within)
                    .order_by(to_outline, *_by_name(Locality))
                )
            )
        ]
        return CampusSurroundings(
            campus=CampusRecord(
                slug=slug,
                city=city_slug,
                name=name,
                location=Point(lat=lat, lng=lng),
                nearest_station=nearby_stations[0] if nearby_stations else None,
            ),
            stations=nearby_stations,
            localities=localities,
        )

    async def _lines(self, station_ids: Collection[int]) -> dict[int, tuple[LineRecord, ...]]:
        """Each station's lines, by name, in one query."""
        if not station_ids:
            return {}
        lines: dict[int, list[LineRecord]] = {}
        for station_id, slug, name, colour in await self._db.execute(
            select(MetroStationLine.station_id, MetroLine.slug, MetroLine.name, MetroLine.colour)
            .join(MetroLine, MetroLine.id == MetroStationLine.line_id)
            .where(MetroStationLine.station_id.in_(station_ids))
            .order_by(MetroStationLine.station_id, *_by_name(MetroLine))
        ):
            lines.setdefault(station_id, []).append(LineRecord(slug=slug, name=name, colour=colour))
        return {station_id: tuple(found) for station_id, found in lines.items()}
