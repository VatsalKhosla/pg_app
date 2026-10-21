"""Points on the Earth and the distances between them. Pure: no I/O.

Coordinates are WGS 84 degrees (SRID 4326), latitude first. Distances are metres.
"""

import math
from dataclasses import dataclass
from typing import Final

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


# A loose box around Delhi NCR, the service area, that catches swapped or mistyped coordinates. It
# is not the region's boundary.
NCR_BOUNDS: Final = Bounds(south=27.0, west=75.5, north=30.0, east=78.5)


def distance_m(a: Point, b: Point) -> float:
    """The great-circle distance (haversine on a sphere). It is within half a percent of the
    distance on the ellipsoid, which is what PostGIS measures."""
    lat_a, lat_b = math.radians(a.lat), math.radians(b.lat)
    half_dlat = (lat_b - lat_a) / 2
    half_dlng = math.radians(b.lng - a.lng) / 2
    h = math.sin(half_dlat) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(half_dlng) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))
