"""The search API's shapes (ARCHITECTURE §10.1, §15; ADR 0028)."""

import uuid
from datetime import date
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.core.schemas import ApiModel
from app.modules.catalog.domain.listing import GenderPolicy, Meals
from app.modules.catalog.domain.rooms import Occupancy
from app.modules.catalog.schemas import LatLng, ListingLocality, PublicMedia
from app.modules.search.domain.query import (
    DEFAULT_RADIUS_M,
    MAX_AMENITIES,
    MAX_RADIUS_M,
    MIN_RADIUS_M,
    TEXT_MAX_LENGTH,
    BedsFree,
    Sort,
)

SLUG: Final = r"^[a-z0-9]+(-[a-z0-9]+)*$"
# Degrees as a browser writes them: up to fifteen decimals.
_NUMBER: Final = r"-?[0-9]{1,3}(\.[0-9]{1,15})?"


class SearchQuery(BaseModel):
    """A search's query parameters, as ARCHITECTURE §10.1 names them; any other is refused."""

    model_config = ConfigDict(extra="forbid")

    campus: str | None = Field(
        default=None, pattern=SLUG, max_length=64, description="Search around this campus."
    )
    radius_m: int = Field(
        default=DEFAULT_RADIUS_M,
        ge=MIN_RADIUS_M,
        le=MAX_RADIUS_M,
        description="How far from the campus, in metres.",
    )
    locality: str | None = Field(
        default=None, pattern=SLUG, max_length=64, description="Search in this locality."
    )
    bbox: str | None = Field(
        default=None,
        pattern=f"^{_NUMBER},{_NUMBER},{_NUMBER},{_NUMBER}$",
        description="Search in this map area: west,south,east,north in degrees.",
    )
    move_in_month: str | None = Field(
        default=None,
        pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$",
        description="YYYY-MM: this month or one of the next six. Prices are for it; this month "
        "if left out.",
    )
    budget_min_paise: int | None = Field(default=None, ge=0)
    budget_max_paise: int | None = Field(default=None, ge=0)
    gender: GenderPolicy | None = None
    occupancy: Occupancy | None = None
    meals: Meals | None = None
    ac: bool = False
    attached_bath: bool = False
    amenities: list[str] = Field(default=[], max_length=MAX_AMENITIES)
    verified_only: bool = Field(
        default=True, description="Only verified PGs; always so while verified_only is on."
    )
    available: bool = Field(default=False, description="Only PGs with a bed free that month.")
    q: str | None = Field(default=None, min_length=1, max_length=TEXT_MAX_LENGTH)
    sort: Sort = Sort.RECOMMENDED
    cursor: str | None = Field(
        default=None, max_length=300, description="The previous page's nextCursor."
    )
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


class StationNearby(ApiModel):
    slug: str
    name: str
    # From the listing's display point.
    distance_m: int


class SearchCard(ApiModel):
    id: uuid.UUID
    slug: str
    name: str
    locality: ListingLocality
    # The display point, 80 to 150 m from the building (ADR 0021).
    display_location: LatLng
    # From the chosen campus to the display point; null without a campus.
    distance_m: int | None
    nearest_station: StationNearby | None
    # What its room categories that match the search come to in the month, in paise.
    min_rent_paise: int
    max_rent_paise: int
    gender_policy: GenderPolicy
    meals: Meals
    verified: bool
    licensed: bool
    cover: PublicMedia | None
    # Roughly how many beds are free that month, from real inventory.
    beds_free: BedsFree


class SearchPage(ApiModel):
    items: list[SearchCard]
    next_cursor: str | None
    # The month the prices are for.
    month: date
