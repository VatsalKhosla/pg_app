"""Where a PG is, and where the public sees it (ARCHITECTURE §10.5).

The exact point is for staff and, once a visit is scheduled or a booking confirmed, for the
student. Everyone else sees a display point: the exact point moved a random 80 to 150 m in a
random direction. It is made once and stored, and made again only when the exact point moves, so
asking many times can't average it away.

Distances shown to the public must be measured from display points too. Exact distances to a few
known places (campuses, stations) would give away the exact point by trilateration.
"""

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from app.core.geometry import EARTH_RADIUS_M, Point

if TYPE_CHECKING:
    from random import Random

MIN_OFFSET_M: Final = 80.0
MAX_OFFSET_M: Final = 150.0
# OpenStreetMap's precision: seven decimals, about a centimetre.
DECIMALS: Final = 7


@dataclass(frozen=True, slots=True)
class Offset:
    # Clockwise from north.
    bearing_deg: float
    distance_m: float


def random_offset(rng: Random) -> Offset:
    """A direction and distance for a display point. Pass a ``secrets.SystemRandom``, so the
    offset can't be predicted."""
    return Offset(
        bearing_deg=rng.uniform(0.0, 360.0), distance_m=rng.uniform(MIN_OFFSET_M, MAX_OFFSET_M)
    )


def moved(point: Point, offset: Offset) -> Point:
    """``point`` moved by ``offset`` along a great circle."""
    lat, lng = math.radians(point.lat), math.radians(point.lng)
    bearing = math.radians(offset.bearing_deg)
    angle = offset.distance_m / EARTH_RADIUS_M
    new_lat = math.asin(
        math.sin(lat) * math.cos(angle) + math.cos(lat) * math.sin(angle) * math.cos(bearing)
    )
    new_lng = lng + math.atan2(
        math.sin(bearing) * math.sin(angle) * math.cos(lat),
        math.cos(angle) - math.sin(lat) * math.sin(new_lat),
    )
    return Point(
        lat=round(math.degrees(new_lat), DECIMALS),
        lng=round((math.degrees(new_lng) + 540.0) % 360.0 - 180.0, DECIMALS),
    )
