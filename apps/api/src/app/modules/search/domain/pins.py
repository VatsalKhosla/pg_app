"""Map pins (ARCHITECTURE §10.2; step 3.3, ADR 0029): every live listing in a map area as a compact
pin, at most 2,000 of them, cached briefly by a snapped area, the zoom and the filters. Pure.

The area is snapped outwards to a grid a quarter of a map tile wide at that zoom, so a small pan
asks for the same area again and finds it cached. Pins just outside the view come too, which the
map clusters with the rest.
"""

import hashlib
import json
import math
from typing import TYPE_CHECKING, Final

from app.core.geometry import Bounds

if TYPE_CHECKING:
    from datetime import date

    from app.modules.search.domain.query import SearchRequest

PIN_CAP: Final = 2_000
MIN_ZOOM: Final = 5
MAX_ZOOM: Final = 20
# Seconds an answer is kept: pins follow a listing's changes within a minute.
PINS_TTL_SECONDS: Final = 60


def snapped(bounds: Bounds, zoom: int) -> Bounds:
    """``bounds`` grown outwards to the zoom's grid: 360° / 2^(zoom + 2) a cell."""
    cell = 360 / (1 << (zoom + 2))

    def down(value: float) -> float:
        return round(math.floor(value / cell) * cell, 7)

    def up(value: float) -> float:
        return round(math.ceil(value / cell) * cell, 7)

    return Bounds(
        south=down(bounds.south),
        west=down(bounds.west),
        north=up(bounds.north),
        east=up(bounds.east),
    )


def cache_key(
    request: SearchRequest, *, area: Bounds, zoom: int, month: date, verified_only: bool
) -> str:
    """The same key for every request that must get the same pins."""
    filters = {
        "budget": [request.budget_min, request.budget_max],
        "gender": request.gender,
        "occupancy": request.occupancy,
        "meals": request.meals,
        "ac": request.ac,
        "attached_bath": request.attached_bath,
        "amenities": sorted(request.amenities),
        "available": request.available,
        "text": request.text,
    }
    digest = hashlib.sha256(json.dumps(filters, sort_keys=True).encode()).hexdigest()[:24]
    place = f"{area.west},{area.south},{area.east},{area.north}"
    return f"pins:v1:{zoom}:{place}:{month.isoformat()}:{int(verified_only)}:{digest}"
