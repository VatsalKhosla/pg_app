"""The geo reference data: which places there are, and where each one's coordinates came from
(ADR 0020).

Two files in ``data/``:

- ``places.toml``, written by hand: each place's slug and name, and the OpenStreetMap element it
  is (metro lines: their Wikidata item).
- ``places.json``, written by ``make geo-refresh`` from it: the coordinates and boundaries from
  OpenStreetMap, and each station's lines from Wikidata. ``make seed`` loads this file. Nobody
  edits it by hand, so no coordinate is ever typed in.

A test fails when the two disagree, so a change to the manifest can't go in without a refresh.
"""

import json
import tomllib
from collections import Counter
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.core.geometry import NCR_BOUNDS, Point
from app.modules.geo.domain.places import (
    HEX_COLOUR_PATTERN,
    NAME_MAX_LENGTH,
    SLUG_MAX_LENGTH,
    SLUG_PATTERN,
    WIKIDATA_ID_PATTERN,
    OsmRef,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

DATA_DIR: Final = Path(__file__).parent / "data"
MANIFEST_PATH: Final = DATA_DIR / "places.toml"
DATA_PATH: Final = DATA_DIR / "places.json"

# Coordinates keep OpenStreetMap's own precision: seven decimals, about a centimetre.
COORDINATE_DECIMALS: Final = 7

Slug = Annotated[
    str, StringConstraints(pattern=f"^{SLUG_PATTERN.pattern}$", max_length=SLUG_MAX_LENGTH)
]
Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_MAX_LENGTH)
]
OsmElement = Annotated[str, StringConstraints(pattern=r"^(node|way|relation)/[1-9][0-9]{0,18}$")]
WikidataId = Annotated[str, StringConstraints(pattern=f"^{WIKIDATA_ID_PATTERN.pattern}$")]
Colour = Annotated[str, StringConstraints(pattern=f"^{HEX_COLOUR_PATTERN.pattern}$")]
# A GeoJSON position: longitude, then latitude.
Position = tuple[float, float]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _in_ncr(point: Point, what: str) -> None:
    if not NCR_BOUNDS.contains(point):
        msg = (
            f"{what} ({point.lat}, {point.lng}) is outside Delhi NCR: "
            "are latitude and longitude swapped?"
        )
        raise ValueError(msg)


class Coordinates(_Strict):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)

    @model_validator(mode="after")
    def _within_ncr(self) -> Self:
        _in_ncr(self.point, "a point")
        return self

    @property
    def point(self) -> Point:
        return Point(lat=self.lat, lng=self.lng)


class MultiPolygon(_Strict):
    """A GeoJSON MultiPolygon: polygons, each an outer ring and any holes, each ring closed."""

    type: Literal["MultiPolygon"]
    coordinates: tuple[tuple[tuple[Position, ...], ...], ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _rings_are_closed(self) -> Self:
        for polygon in self.coordinates:
            if not polygon:
                msg = "a polygon needs an outer ring"
                raise ValueError(msg)
            for ring in polygon:
                if len(ring) < 4 or ring[0] != ring[-1]:
                    msg = "each ring needs at least four positions and ends where it starts"
                    raise ValueError(msg)
                for lng, lat in ring:
                    _in_ncr(Point(lat=lat, lng=lng), "a boundary position")
        return self


def _osm(raw: str) -> OsmRef:
    return OsmRef.parse(raw)


def _duplicates(slugs: Iterable[str]) -> list[str]:
    return sorted(slug for slug, count in Counter(slugs).items() if count > 1)


def _check_references(
    *,
    cities: Iterable[str],
    places: Iterable[tuple[str, str]],
    kinds: dict[str, Iterable[str]],
) -> None:
    """Slugs are unique within each kind, and every locality and campus is in a known city."""
    for kind, slugs in kinds.items():
        if duplicated := _duplicates(slugs):
            msg = f"{kind}: slugs used twice: {', '.join(duplicated)}"
            raise ValueError(msg)
    known = set(cities)
    if unknown := sorted({f"{slug} ({city})" for slug, city in places if city not in known}):
        msg = f"places in a city that isn't listed: {', '.join(unknown)}"
        raise ValueError(msg)


# The manifest (places.toml), written by hand.


class ManifestCity(_Strict):
    slug: Slug
    name: Name
    osm: OsmElement


class ManifestPlace(_Strict):
    """A locality or a campus."""

    slug: Slug
    city: Slug
    name: Name
    osm: OsmElement


class ManifestLine(_Strict):
    slug: Slug
    name: Name
    wikidata: WikidataId


class ManifestStation(_Strict):
    slug: Slug
    name: Name
    osm: OsmElement


class Manifest(_Strict):
    cities: tuple[ManifestCity, ...]
    localities: tuple[ManifestPlace, ...]
    campuses: tuple[ManifestPlace, ...]
    metro_lines: tuple[ManifestLine, ...]
    metro_stations: tuple[ManifestStation, ...]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        _check_references(
            cities=(city.slug for city in self.cities),
            places=[
                *((place.slug, place.city) for place in self.localities),
                *((place.slug, place.city) for place in self.campuses),
            ],
            kinds={
                "cities": (row.slug for row in self.cities),
                "localities": (row.slug for row in self.localities),
                "campuses": (row.slug for row in self.campuses),
                "metro lines": (row.slug for row in self.metro_lines),
                "metro stations": (row.slug for row in self.metro_stations),
            },
        )
        if duplicated := _duplicates(line.wikidata for line in self.metro_lines):
            msg = f"metro lines: Wikidata items used twice: {', '.join(duplicated)}"
            raise ValueError(msg)
        return self


def read_manifest(path: Path = MANIFEST_PATH) -> Manifest:
    return Manifest.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))


# The data (places.json), written by `make geo-refresh`.


class Source(_Strict):
    name: Name
    provides: str
    licence: str
    url: str
    attribution: str | None = None


class City(_Strict):
    slug: Slug
    name: Name
    osm: OsmElement
    center: Coordinates

    @property
    def osm_ref(self) -> OsmRef:
        return _osm(self.osm)


class Locality(_Strict):
    slug: Slug
    city: Slug
    name: Name
    osm: OsmElement
    center: Coordinates
    # From the element's own outline; none for a place mapped as a single point.
    boundary: MultiPolygon | None

    @property
    def osm_ref(self) -> OsmRef:
        return _osm(self.osm)


class Campus(_Strict):
    slug: Slug
    city: Slug
    name: Name
    osm: OsmElement
    location: Coordinates

    @property
    def osm_ref(self) -> OsmRef:
        return _osm(self.osm)


class MetroLine(_Strict):
    slug: Slug
    name: Name
    wikidata: WikidataId
    colour: Colour


class MetroStation(_Strict):
    slug: Slug
    name: Name
    osm: OsmElement
    wikidata: WikidataId
    location: Coordinates
    lines: tuple[Slug, ...] = Field(min_length=1)

    @property
    def osm_ref(self) -> OsmRef:
        return _osm(self.osm)


class ReferenceData(_Strict):
    retrieved_on: date
    sources: tuple[Source, ...] = Field(min_length=1)
    cities: tuple[City, ...]
    localities: tuple[Locality, ...]
    campuses: tuple[Campus, ...]
    metro_lines: tuple[MetroLine, ...]
    metro_stations: tuple[MetroStation, ...]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        _check_references(
            cities=(city.slug for city in self.cities),
            places=[
                *((place.slug, place.city) for place in self.localities),
                *((place.slug, place.city) for place in self.campuses),
            ],
            kinds={
                "cities": (row.slug for row in self.cities),
                "localities": (row.slug for row in self.localities),
                "campuses": (row.slug for row in self.campuses),
                "metro lines": (row.slug for row in self.metro_lines),
                "metro stations": (row.slug for row in self.metro_stations),
            },
        )
        lines = {line.slug for line in self.metro_lines}
        for station in self.metro_stations:
            if unknown := sorted(set(station.lines) - lines):
                msg = f"{station.slug}: lines that aren't listed: {', '.join(unknown)}"
                raise ValueError(msg)
            if len(set(station.lines)) != len(station.lines):
                msg = f"{station.slug}: a line is listed twice"
                raise ValueError(msg)
        return self


def read_reference_data(path: Path = DATA_PATH) -> ReferenceData:
    return ReferenceData.model_validate_json(path.read_bytes())


def manifest_differences(manifest: Manifest, data: ReferenceData) -> list[str]:
    """How the data differs from the manifest it should have been made from: empty when
    ``make geo-refresh`` has run since the manifest last changed."""

    def described(rows: Iterable[BaseModel], fields: tuple[str, ...]) -> list[tuple[object, ...]]:
        return [tuple(getattr(row, name) for name in fields) for row in rows]

    place = ("slug", "city", "name", "osm")
    pairs = {
        "cities": (manifest.cities, data.cities, ("slug", "name", "osm")),
        "localities": (manifest.localities, data.localities, place),
        "campuses": (manifest.campuses, data.campuses, place),
        "metro lines": (manifest.metro_lines, data.metro_lines, ("slug", "name", "wikidata")),
        "metro stations": (manifest.metro_stations, data.metro_stations, ("slug", "name", "osm")),
    }
    return [
        kind
        for kind, (wanted, made, fields) in pairs.items()
        if described(wanted, fields) != described(made, fields)
    ]


def dump_reference_data(data: ReferenceData) -> str:
    """places.json's text: one place per line, so a refresh's diff shows which places moved."""
    document = data.model_dump(mode="json", exclude_none=False)
    lines = ["{"]
    keys = list(document)
    for index, key in enumerate(keys):
        value = document[key]
        comma = "," if index < len(keys) - 1 else ""
        if isinstance(value, list):
            rows = [f"    {json.dumps(row, ensure_ascii=False)}" for row in value]
            body = ",\n".join(rows)
            lines.append(f'  "{key}": [\n{body}\n  ]{comma}' if rows else f'  "{key}": []{comma}')
        else:
            lines.append(f'  "{key}": {json.dumps(value, ensure_ascii=False)}{comma}')
    lines.append("}")
    return "\n".join(lines) + "\n"
