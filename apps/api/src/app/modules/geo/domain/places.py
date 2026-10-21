"""The places people choose a PG by (ARCHITECTURE §6): cities, their localities, campuses and
metro stations.

Every coordinate comes from OpenStreetMap and is never typed in (ADR 0020), so each place keeps a
reference to the element it came from. Coordinates are WGS 84 degrees (SRID 4326); code puts
latitude first, GeoJSON puts longitude first. Distances are metres.
"""

import math
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

SLUG_PATTERN: Final = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
SLUG_MAX_LENGTH: Final = 64
NAME_MAX_LENGTH: Final = 120
WIKIDATA_ID_PATTERN: Final = re.compile(r"Q[1-9][0-9]*")
HEX_COLOUR_PATTERN: Final = re.compile(r"#[0-9A-F]{6}")

# What a campus page shows around it: localities within the 2 km a first micro-market maps
# (PRODUCT_CONTEXT §8), and the closest metro stations within it.
NEARBY_RADIUS_M: Final = 2_000
NEAREST_STATIONS: Final = 3

# The mean Earth radius (IUGG), for great-circle distances.
EARTH_RADIUS_M: Final = 6_371_008.8


@dataclass(frozen=True, slots=True)
class Point:
    lat: float
    lng: float


@dataclass(frozen=True, slots=True)
class Bounds:
    south: float
    west: float
    north: float
    east: float

    def contains(self, point: Point) -> bool:
        return self.south <= point.lat <= self.north and self.west <= point.lng <= self.east


# A loose box around Delhi NCR that catches swapped or mistyped coordinates. It is not the
# region's boundary.
NCR_BOUNDS: Final = Bounds(south=27.0, west=75.5, north=30.0, east=78.5)


class OsmType(StrEnum):
    NODE = "node"
    WAY = "way"
    RELATION = "relation"


_OSM_REF: Final = re.compile(r"(node|way|relation)/([1-9][0-9]{0,18})")


@dataclass(frozen=True, slots=True)
class OsmRef:
    """An OpenStreetMap element, such as ``relation/3859752``: where a place's coordinates came
    from."""

    type: OsmType
    id: int

    @classmethod
    def parse(cls, raw: str) -> OsmRef:
        match = _OSM_REF.fullmatch(raw)
        if match is None:
            msg = f"not an OpenStreetMap element (like relation/3859752): {raw!r}"
            raise ValueError(msg)
        return cls(OsmType(match.group(1)), int(match.group(2)))

    def __str__(self) -> str:
        return f"{self.type}/{self.id}"

    @property
    def url(self) -> str:
        return f"https://www.openstreetmap.org/{self}"


def distance_m(a: Point, b: Point) -> float:
    """The great-circle distance (haversine on a sphere). It is within half a percent of the
    distance on the ellipsoid, which is what PostGIS measures."""
    lat_a, lat_b = math.radians(a.lat), math.radians(b.lat)
    half_dlat = (lat_b - lat_a) / 2
    half_dlng = math.radians(b.lng - a.lng) / 2
    h = math.sin(half_dlat) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(half_dlng) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))
