"""Searching listings (ARCHITECTURE §10.1; step 3.2, ADR 0028): what a search may ask, how its
pages are cut, and what a card says about free beds. Pure: no database, no clock.
"""

import base64
import binascii
import json
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from app.core.geometry import NCR_BOUNDS, Bounds, Point

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date

    from app.core.money import Paise

DEFAULT_RADIUS_M: Final = 3_000
MIN_RADIUS_M: Final = 200
MAX_RADIUS_M: Final = 15_000
TEXT_MAX_LENGTH: Final = 100
MAX_AMENITIES: Final = 20


class Sort(StrEnum):
    RECOMMENDED = "recommended"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    DISTANCE = "distance"
    NEWEST = "newest"


class Order(StrEnum):
    """How a page is really ordered: ``recommended`` stands for one of the others."""

    RELEVANCE = "relevance"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    DISTANCE = "distance"
    NEWEST = "newest"


def order_for(sort: Sort, *, has_text: bool, has_campus: bool) -> Order:
    """``recommended`` is, for now, the best match for the words searched, else the nearest to
    the chosen campus, else the newest."""
    if sort is not Sort.RECOMMENDED:
        return Order(sort.value)
    if has_text:
        return Order.RELEVANCE
    return Order.DISTANCE if has_campus else Order.NEWEST


@dataclass(frozen=True, slots=True)
class Cursor:
    """Where the next page starts: the last card's place in the order (its sort key, then its
    id, so ties are broken the same way every time)."""

    order: Order
    key: int | float | str
    after: uuid.UUID


@dataclass(frozen=True, slots=True)
class SearchRequest:
    # At most one place to search around: a campus (within a radius), a locality or a box.
    campus: str | None = None
    radius_m: int = DEFAULT_RADIUS_M
    locality: str | None = None
    bbox: Bounds | None = None
    # The month the student moves in, and the rent they can pay that month.
    month: date | None = None
    budget_min: Paise | None = None
    budget_max: Paise | None = None
    gender: str | None = None
    occupancy: str | None = None
    meals: str | None = None
    ac: bool = False
    attached_bath: bool = False
    amenities: tuple[str, ...] = ()
    verified_only: bool = True
    available: bool = False
    text: str | None = None
    sort: Sort = Sort.RECOMMENDED
    cursor: str | None = None
    limit: int = 20


def request_problems(request: SearchRequest, *, months: Sequence[date]) -> list[str]:
    """What makes a search impossible to answer; ``months`` are those with price summaries."""
    problems = []
    places = [request.campus, request.locality, request.bbox]
    if sum(place is not None for place in places) > 1:
        problems.append("search around one place: a campus, a locality or a map area")
    if request.sort is Sort.DISTANCE and request.campus is None:
        problems.append("sorting by distance needs a campus")
    if not MIN_RADIUS_M <= request.radius_m <= MAX_RADIUS_M:
        problems.append(f"the radius must be from {MIN_RADIUS_M} m to {MAX_RADIUS_M} m")
    if (
        request.budget_min is not None
        and request.budget_max is not None
        and request.budget_min > request.budget_max
    ):
        problems.append("the lowest budget is more than the highest")
    if request.month is not None and request.month not in months:
        problems.append("prices are known for this month and the next six only")
    if request.bbox is not None:
        box = request.bbox
        if not (box.west < box.east and box.south < box.north):
            problems.append("the map area's west and south must be less than its east and north")
        elif not (
            NCR_BOUNDS.contains(Point(lat=box.south, lng=box.west))
            and NCR_BOUNDS.contains(Point(lat=box.north, lng=box.east))
        ):
            problems.append("the map area must be inside Delhi NCR")
    return problems


def encode_cursor(cursor: Cursor) -> str:
    raw = json.dumps([cursor.order.value, cursor.key, str(cursor.after)], separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(text: str) -> Cursor | None:
    """The cursor ``encode_cursor`` made, or None for anything else (it isn't trusted)."""
    try:
        raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
        order, key, after = json.loads(raw)
        if not isinstance(key, int | float | str) or isinstance(key, bool):
            return None
        return Cursor(order=Order(order), key=key, after=uuid.UUID(after))
    except binascii.Error, ValueError, TypeError, UnicodeDecodeError:
        return None


class BedsFree(StrEnum):
    """How many beds are free that month, roughly: real inventory (CLAUDE.md rule 7), without
    handing out exact counts."""

    NONE = "none"
    FEW = "few"
    SOME = "some"
    MANY = "many"


def beds_free(count: int) -> BedsFree:
    if count <= 0:
        return BedsFree.NONE
    if count <= 2:
        return BedsFree.FEW
    if count < 10:
        return BedsFree.SOME
    return BedsFree.MANY
