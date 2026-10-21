"""Refresh the geo reference data from OpenStreetMap and Wikidata: ``make geo-refresh``.

It reads ``data/places.toml``, looks up every element the file names, and writes
``data/places.json`` (see ``app.modules.geo.reference``). Run it by hand when the manifest
changes and review the diff. Never run it in CI or tests: it calls public services that ask to
be used lightly.

- **OpenStreetMap**, through Nominatim's ``/lookup``, under Nominatim's usage policy
  (https://operations.osmfoundation.org/policies/nominatim/):
  - one request at a time, at most one a second;
  - a User-Agent that says who is asking;
  - results kept: places.json is the cache.

  It never searches. Choosing the right element is a person's job, done once per place.
- **Wikidata**, for each metro station's lines (P81, "connecting line") and each line's colour
  (P465), under the API etiquette (https://www.mediawiki.org/wiki/API:Etiquette): requests one
  after another, with ``maxlag``.

It refuses rather than guess when:
- an element is missing;
- a "station" isn't a metro station;
- OpenStreetMap and Wikidata put a station more than 300 m apart;
- a station is on a line the manifest doesn't list. It then prints the entry to add.
"""

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.clock import SystemClock, today_in_india
from app.modules.geo.domain.places import WIKIDATA_ID_PATTERN, Point, distance_m
from app.modules.geo.reference import (
    COORDINATE_DECIMALS,
    DATA_PATH,
    MANIFEST_PATH,
    Campus,
    City,
    Coordinates,
    Locality,
    Manifest,
    ManifestCity,
    ManifestPlace,
    MetroLine,
    MetroStation,
    MultiPolygon,
    ReferenceData,
    Source,
    dump_reference_data,
    read_manifest,
    read_reference_data,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence
    from typing import TextIO

USER_AGENT: Final = "pg-platform-geo-refresh/1.0 (+https://github.com/VatsalKhosla/pg_app)"
NOMINATIM_LOOKUP: Final = "https://nominatim.openstreetmap.org/lookup"
WIKIDATA_API: Final = "https://www.wikidata.org/w/api.php"
TIMEOUT: Final = httpx.Timeout(10.0, connect=3.0)

# Both services take at most 50 ids a request.
BATCH: Final = 50
# At most one request a second, to either service.
MIN_INTERVAL_S: Final = 1.0
RETRIES: Final = 3
BACKOFF_S: Final = 2.0
RETRY_STATUSES: Final = frozenset({429, 500, 502, 503, 504})
# Answers are kept on disk for a day, so running again after a manifest change asks only for what
# changed (Nominatim's policy asks for caching). --fresh ignores them.
CACHE_DIR: Final = Path(__file__).resolve().parents[4] / ".cache" / "geo-refresh"
CACHE_MAX_AGE_S: Final = 24 * 60 * 60
# Nominatim simplifies outlines to about 5 m before sending them (degrees).
POLYGON_THRESHOLD: Final = "0.00005"
# OpenStreetMap and Wikidata may place a station at different ends of its platforms, no further.
STATION_AGREEMENT_M: Final = 300
STATION_TAGS: Final = frozenset({"subway", "light_rail", "monorail"})

CONNECTING_LINE: Final = "P81"
COORDINATES: Final = "P625"
COLOUR: Final = "P465"
START_TIME: Final = "P580"
END_TIME: Final = "P582"

SOURCES: Final = (
    Source(
        name="OpenStreetMap",
        provides="every coordinate and boundary, looked up through Nominatim",
        licence="ODbL-1.0",
        url="https://www.openstreetmap.org/copyright",
        attribution="© OpenStreetMap contributors",
    ),
    Source(
        name="Wikidata",
        provides="each metro station's lines (P81) and each line's colour (P465)",
        licence="CC0-1.0",
        url="https://www.wikidata.org/wiki/Wikidata:Licensing",
    ),
)


class RefreshError(Exception):
    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = list(problems)


class Throttle:
    """At most one request per ``interval`` seconds."""

    def __init__(
        self,
        interval: float = MIN_INTERVAL_S,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._interval = interval
        self._monotonic = monotonic
        self._sleep = sleep
        self._last: float | None = None

    def wait(self) -> None:
        now = self._monotonic()
        if self._last is not None and (gap := self._last + self._interval - now) > 0:
            self._sleep(gap)
            now += gap
        self._last = now


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After", "")
    return float(value) if value.isdigit() else None


class ResponseCache:
    """JSON answers on disk, by request, until they are ``max_age_s`` old."""

    def __init__(
        self,
        directory: Path,
        *,
        max_age_s: float = CACHE_MAX_AGE_S,
        now: Callable[[], float] = lambda: SystemClock().now().timestamp(),
    ) -> None:
        self._directory = directory
        self._max_age_s = max_age_s
        self._now = now

    def _path(self, url: str, params: dict[str, str]) -> Path:
        key = f"{url}?{urlencode(sorted(params.items()))}"
        return self._directory / f"{hashlib.sha256(key.encode()).hexdigest()}.json"

    def get(self, url: str, params: dict[str, str]) -> Any:
        path = self._path(url, params)
        try:
            if self._now() - path.stat().st_mtime > self._max_age_s:
                return None
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError, ValueError:
            return None

    def put(self, url: str, params: dict[str, str], body: object) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        self._path(url, params).write_text(json.dumps(body), encoding="utf-8")


class Fetcher:
    """GETs JSON one request at a time, with retries and backoff for the transient failures,
    from the cache when it has the answer."""

    def __init__(
        self,
        http: httpx.Client,
        throttle: Throttle,
        *,
        sleep: Callable[[float], None] = time.sleep,
        cache: ResponseCache | None = None,
    ) -> None:
        self._http = http
        self._throttle = throttle
        self._sleep = sleep
        self._cache = cache

    def get(self, url: str, params: dict[str, str]) -> Any:
        if self._cache is not None and (kept := self._cache.get(url, params)) is not None:
            return kept
        body = self._fetch(url, params)
        if self._cache is not None:
            self._cache.put(url, params, body)
        return body

    def _fetch(self, url: str, params: dict[str, str]) -> Any:
        for attempt in range(RETRIES + 1):
            last = attempt == RETRIES
            self._throttle.wait()
            try:
                response = self._http.get(url, params=params)
            except httpx.TransportError as error:
                if last:
                    raise RefreshError([f"{url}: {error!r}"]) from error
                self._sleep(BACKOFF_S * 2**attempt)
                continue
            if response.status_code in RETRY_STATUSES and not last:
                self._sleep(_retry_after(response) or BACKOFF_S * 2**attempt)
                continue
            if response.status_code != httpx.codes.OK:
                raise RefreshError([f"{url} answered {response.status_code}"])
            body = response.json()
            # Wikidata refuses with maxlag while its replicas lag behind; it says when to retry.
            if isinstance(body, dict) and body.get("error", {}).get("code") == "maxlag":
                if last:
                    raise RefreshError([f"{url}: Wikidata is busy (maxlag); try again later"])
                self._sleep(_retry_after(response) or BACKOFF_S * 2**attempt)
                continue
            return body
        raise AssertionError  # pragma: no cover - the loop returns or raises


# What Nominatim and Wikidata answer, as far as this reads it.


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class _Geometry(_Lenient):
    type: str
    coordinates: Any


class _Place(_Lenient):
    osm_type: Literal["node", "way", "relation"]
    osm_id: int
    lat: float
    lon: float
    category: str
    type: str
    name: str = ""
    namedetails: dict[str, str] | None = None
    extratags: dict[str, str] | None = None
    geojson: _Geometry | None = None

    @property
    def ref(self) -> str:
        return f"{self.osm_type}/{self.osm_id}"

    @property
    def tags(self) -> dict[str, str]:
        return self.extratags or {}

    @property
    def osm_name(self) -> str:
        return (self.namedetails or {}).get("name:en") or self.name


class _DataValue(_Lenient):
    value: Any


class _Snak(_Lenient):
    snaktype: str
    datavalue: _DataValue | None = None


class _Statement(_Lenient):
    mainsnak: _Snak
    rank: str
    qualifiers: dict[str, list[_Snak]] = {}


class _Label(_Lenient):
    value: str


class _Entity(_Lenient):
    claims: dict[str, list[_Statement]] = {}
    labels: dict[str, _Label] = {}
    missing: str | None = None


class _Entities(_Lenient):
    entities: dict[str, _Entity]


def _batches(items: Sequence[str]) -> Iterable[Sequence[str]]:
    return (items[start : start + BATCH] for start in range(0, len(items), BATCH))


def _lookup(fetcher: Fetcher, refs: Iterable[str], *, outlines: bool) -> dict[str, _Place]:
    letters = {"node": "N", "way": "W", "relation": "R"}
    ids = sorted({letters[ref.split("/")[0]] + ref.split("/")[1] for ref in refs})
    found: dict[str, _Place] = {}
    for batch in _batches(ids):
        params = {
            "osm_ids": ",".join(batch),
            "format": "jsonv2",
            "extratags": "1",
            "namedetails": "1",
        }
        if outlines:
            params |= {"polygon_geojson": "1", "polygon_threshold": POLYGON_THRESHOLD}
        for raw in fetcher.get(NOMINATIM_LOOKUP, params):
            place = _Place.model_validate(raw)
            found[place.ref] = place
    return found


def _entities(fetcher: Fetcher, ids: Iterable[str], *, props: str) -> dict[str, _Entity]:
    found: dict[str, _Entity] = {}
    for batch in _batches(sorted(set(ids))):
        params = {
            "action": "wbgetentities",
            "ids": "|".join(batch),
            "props": props,
            "languages": "en",
            "format": "json",
            "maxlag": "5",
        }
        found |= _Entities.model_validate(fetcher.get(WIKIDATA_API, params)).entities
    return found


def _date(snak: _Snak) -> date | None:
    """A Wikidata time's date, at whatever precision it has (a missing month or day is 1)."""
    value = snak.datavalue.value if snak.datavalue else None
    if not isinstance(value, dict):
        return None
    match = re.fullmatch(r"\+(\d{4})-(\d{2})-(\d{2})T.*", str(value.get("time", "")))
    if match is None:
        return None
    year, month, day = (int(part) for part in match.groups())
    return date(year, max(month, 1), max(day, 1))


def _current(statements: Iterable[_Statement], *, today: date) -> list[_Statement]:
    """Statements that hold today: not deprecated, already started and not yet ended."""
    current = []
    for statement in statements:
        if statement.rank == "deprecated" or statement.mainsnak.snaktype != "value":
            continue
        started = [_date(snak) for snak in statement.qualifiers.get(START_TIME, [])]
        if any(day is not None and day > today for day in started):
            continue
        ended = [_date(snak) for snak in statement.qualifiers.get(END_TIME, [])]
        if any(day is None or day <= today for day in ended):
            continue
        current.append(statement)
    preferred = [statement for statement in current if statement.rank == "preferred"]
    return preferred or current


def _items(entity: _Entity, prop: str, *, today: date) -> list[str]:
    values = []
    for statement in _current(entity.claims.get(prop, []), today=today):
        value = statement.mainsnak.datavalue.value if statement.mainsnak.datavalue else None
        if isinstance(value, dict) and isinstance(value.get("id"), str):
            values.append(value["id"])
    return values


def _point(entity: _Entity, *, today: date) -> Point | None:
    for statement in _current(entity.claims.get(COORDINATES, []), today=today):
        value = statement.mainsnak.datavalue.value if statement.mainsnak.datavalue else None
        if isinstance(value, dict):
            return Point(lat=float(value["latitude"]), lng=float(value["longitude"]))
    return None


def _colour(entity: _Entity, *, today: date) -> str | None:
    for statement in _current(entity.claims.get(COLOUR, []), today=today):
        value = statement.mainsnak.datavalue.value if statement.mainsnak.datavalue else None
        if isinstance(value, str) and re.fullmatch(r"[0-9A-Fa-f]{6}", value):
            return f"#{value.upper()}"
    return None


def _coordinates(place: _Place) -> Coordinates:
    return Coordinates(
        lat=round(place.lat, COORDINATE_DECIMALS), lng=round(place.lon, COORDINATE_DECIMALS)
    )


def _boundary(geometry: _Geometry | None) -> MultiPolygon | None:
    """The element's outline as a MultiPolygon, or None for a point or a line. Rings that
    simplification left too small to be rings are dropped."""
    if geometry is None:
        return None
    match geometry.type:
        case "Polygon":
            polygons = [geometry.coordinates]
        case "MultiPolygon":
            polygons = geometry.coordinates
        case _:
            return None
    kept = []
    for polygon in polygons:
        rings = [
            tuple(
                (round(float(lng), COORDINATE_DECIMALS), round(float(lat), COORDINATE_DECIMALS))
                for lng, lat, *_ in ring
            )
            for ring in polygon
        ]
        if rings and len(rings[0]) >= 4:
            kept.append(tuple(ring for ring in rings if len(ring) >= 4))
    return MultiPolygon(type="MultiPolygon", coordinates=tuple(kept)) if kept else None


def _is_metro_station(place: _Place) -> bool:
    tags = place.tags
    return (place.category, place.type) == ("railway", "station") and (
        tags.get("station") in STATION_TAGS
        or tags.get("subway") == "yes"
        or tags.get("light_rail") == "yes"
    )


def _same_name(ours: str, theirs: str) -> bool:
    def simple(name: str) -> str:
        return re.sub(r"[^a-z0-9]", "", name.casefold())

    return simple(ours) == simple(theirs)


def _suggested_slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.casefold()).strip("-")[:64] or "line"


class _Refresh:
    def __init__(self, manifest: Manifest, *, fetcher: Fetcher, today: date) -> None:
        self.manifest = manifest
        self.fetcher = fetcher
        self.today = today
        self.problems: list[str] = []
        self.notes: list[str] = []
        self.places: dict[str, _Place] = {}

    def place(self, ref: str, what: str, *, name: str) -> _Place | None:
        place = self.places.get(ref)
        if place is None:
            self.problems.append(
                f"{what}: Nominatim has no {ref}; check the element on openstreetmap.org"
            )
        elif place.osm_name and not _same_name(name, place.osm_name):
            self.notes.append(f'{what} "{name}": OpenStreetMap calls it "{place.osm_name}"')
        return place

    def run(self) -> ReferenceData:
        manifest = self.manifest
        outlined = {row.osm for row in manifest.localities}
        plain = {
            *(row.osm for row in manifest.cities),
            *(row.osm for row in manifest.campuses),
            *(row.osm for row in manifest.metro_stations),
        } - outlined
        self.places = _lookup(self.fetcher, outlined, outlines=True) | _lookup(
            self.fetcher, plain, outlines=False
        )
        cities = [city for row in manifest.cities if (city := self.city(row))]
        localities = [place for row in manifest.localities if (place := self.locality(row))]
        campuses = [campus for row in manifest.campuses if (campus := self.campus(row))]
        lines, stations = self.metro()
        if self.problems:
            raise RefreshError(self.problems)
        return ReferenceData(
            retrieved_on=self.today,
            sources=SOURCES,
            cities=tuple(cities),
            localities=tuple(localities),
            campuses=tuple(campuses),
            metro_lines=tuple(lines),
            metro_stations=tuple(stations),
        )

    def city(self, row: ManifestCity) -> City | None:
        found = self.place(row.osm, f"city {row.slug}", name=row.name)
        if found is None:
            return None
        return City(slug=row.slug, name=row.name, osm=row.osm, center=_coordinates(found))

    def locality(self, row: ManifestPlace) -> Locality | None:
        found = self.place(row.osm, f"locality {row.slug}", name=row.name)
        if found is None:
            return None
        boundary = _boundary(found.geojson)
        if boundary is None:
            self.notes.append(f"locality {row.slug}: mapped as a point, so no boundary")
        return Locality(
            slug=row.slug,
            city=row.city,
            name=row.name,
            osm=row.osm,
            center=_coordinates(found),
            boundary=boundary,
        )

    def campus(self, row: ManifestPlace) -> Campus | None:
        found = self.place(row.osm, f"campus {row.slug}", name=row.name)
        if found is None:
            return None
        return Campus(
            slug=row.slug, city=row.city, name=row.name, osm=row.osm, location=_coordinates(found)
        )

    def metro(self) -> tuple[list[MetroLine], list[MetroStation]]:
        items = self.station_items()
        on_lines, unknown = self.station_lines(items)
        lines = self.lines(unknown)
        stations = [
            MetroStation(
                slug=row.slug,
                name=row.name,
                osm=row.osm,
                wikidata=items[row.slug][0],
                location=_coordinates(items[row.slug][1]),
                lines=tuple(on_lines[row.slug]),
            )
            for row in self.manifest.metro_stations
            if on_lines.get(row.slug)
        ]
        return lines, stations

    def station_items(self) -> dict[str, tuple[str, _Place]]:
        """Each metro station's Wikidata item and OpenStreetMap element, once both check out."""
        items: dict[str, tuple[str, _Place]] = {}
        for row in self.manifest.metro_stations:
            what = f"metro station {row.slug}"
            found = self.place(row.osm, what, name=row.name)
            if found is None:
                continue
            if not _is_metro_station(found):
                network = found.tags.get("network", "no network")
                self.problems.append(
                    f"{what}: {row.osm} is {found.category}={found.type} ({network}), "
                    "not a metro station"
                )
                continue
            item = found.tags.get("wikidata", "")
            if not WIKIDATA_ID_PATTERN.fullmatch(item):
                self.problems.append(f"{what}: {row.osm} has no Wikidata item to read lines from")
                continue
            items[row.slug] = (item, found)
        return items

    def station_lines(
        self, items: dict[str, tuple[str, _Place]]
    ) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        """Each station's lines (our slugs, in the manifest's order), and the lines the manifest
        doesn't list with the stations on them. Also compares OpenStreetMap's and Wikidata's
        positions for each station."""
        known = {line.wikidata: line.slug for line in self.manifest.metro_lines}
        entities = _entities(self.fetcher, (item for item, _ in items.values()), props="claims")
        on_lines: dict[str, list[str]] = {}
        unknown: dict[str, list[str]] = {}
        for slug, (item, found) in items.items():
            what = f"metro station {slug}"
            entity = entities.get(item)
            if entity is None or entity.missing is not None:
                self.problems.append(f"{what}: Wikidata has no {item}")
                continue
            served_by = _items(entity, CONNECTING_LINE, today=self.today)
            if not served_by:
                self.problems.append(f"{what}: Wikidata ({item}) lists no line (P81)")
            for line in served_by:
                if line not in known:
                    unknown.setdefault(line, []).append(slug)
            on_lines[slug] = [known[line] for line in known if line in served_by]
            elsewhere = _point(entity, today=self.today)
            if elsewhere is None:
                self.notes.append(f"{what}: Wikidata ({item}) has no coordinates to compare")
            elif (apart := distance_m(_coordinates(found).point, elsewhere)) > STATION_AGREEMENT_M:
                self.problems.append(
                    f"{what}: OpenStreetMap and Wikidata ({item}) are {apart:.0f} m apart"
                )
        return on_lines, unknown

    def lines(self, unknown: dict[str, list[str]]) -> list[MetroLine]:
        """The manifest's lines with their colours; each unknown line becomes a problem that
        says how to add it."""
        known = self.manifest.metro_lines
        entities = _entities(
            self.fetcher, [*(line.wikidata for line in known), *unknown], props="labels|claims"
        )
        for item, slugs in sorted(unknown.items()):
            entity = entities.get(item)
            label = entity.labels["en"].value if entity and "en" in entity.labels else item
            self.problems.append(
                f"{', '.join(slugs)}: on {label} ({item}), which places.toml doesn't list. "
                f'If it is a line, add:\n[[metro_lines]]\nslug = "{_suggested_slug(label)}"\n'
                f'name = "{label}"\nwikidata = "{item}"'
            )
        lines = []
        for line in known:
            entity = entities.get(line.wikidata)
            colour = None if entity is None else _colour(entity, today=self.today)
            if colour is None:
                self.problems.append(f"metro line {line.slug}: no colour (P465) on Wikidata")
                continue
            lines.append(
                MetroLine(slug=line.slug, name=line.name, wikidata=line.wikidata, colour=colour)
            )
        return lines


def http_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """The client every request goes through: it says who is asking."""
    return httpx.Client(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}, transport=transport)


def refresh(
    manifest: Manifest, *, fetcher: Fetcher, today: date
) -> tuple[ReferenceData, list[str]]:
    """The reference data the manifest describes, and notes for whoever reviews it."""
    run = _Refresh(manifest, fetcher=fetcher, today=today)
    try:
        data = run.run()
    except ValidationError as error:
        raise RefreshError([f"the result isn't valid reference data: {error}"]) from error
    return data, run.notes


def _unchanged(path: Path, data: ReferenceData) -> bool:
    try:
        existing = read_reference_data(path)
    except FileNotFoundError, ValidationError:
        return False
    return existing.model_copy(update={"retrieved_on": data.retrieved_on}) == data


def main(argv: Sequence[str] | None = None, *, out: TextIO = sys.stdout) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.modules.geo.refresh",
        description="Write places.json from places.toml, OpenStreetMap and Wikidata.",
    )
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--out", type=Path, default=DATA_PATH)
    parser.add_argument("--fresh", action="store_true", help="ignore answers kept from earlier")
    args = parser.parse_args(argv)
    manifest = read_manifest(args.manifest)
    out_path: Path = args.out
    with http_client() as http:
        try:
            data, notes = refresh(
                manifest,
                fetcher=Fetcher(
                    http, Throttle(), cache=None if args.fresh else ResponseCache(CACHE_DIR)
                ),
                today=today_in_india(SystemClock()),
            )
        except RefreshError as error:
            out.write("Not refreshed:\n")
            out.writelines(f"- {problem}\n" for problem in error.problems)
            return 1
    out.writelines(f"note: {note}\n" for note in notes)
    if _unchanged(out_path, data):
        out.write(f"Nothing changed: {out_path} stays as it is.\n")
        return 0
    out_path.write_text(dump_reference_data(data), encoding="utf-8")
    out.write(
        f"Wrote {out_path}: {len(data.cities)} cities, {len(data.localities)} localities, "
        f"{len(data.campuses)} campuses, {len(data.metro_lines)} metro lines and "
        f"{len(data.metro_stations)} stations. Review the diff before committing.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
