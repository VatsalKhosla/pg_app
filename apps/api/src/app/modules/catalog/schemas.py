"""Catalog requests and responses (ARCHITECTURE §15). Money is integer paise in fields ending in
``Paise``. These are staff views: the exact location and the address appear here, never in a
public response."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from app.core.schemas import ApiModel
from app.modules.catalog.domain.charges import LABEL_MAX_LENGTH, UNIT_MAX_LENGTH, ChargeKind
from app.modules.catalog.domain.listing import (
    GenderPolicy,
    LicenceStatus,
    LocationPrecision,
    Meals,
    PropertyStatus,
    SocietyPermission,
    VerificationStatus,
)
from app.modules.catalog.domain.owners import KycStatus, OwnerStatus
from app.modules.catalog.domain.rooms import BedStatus, CategoryStatus, Occupancy

Paise = Annotated[int, Field(ge=0)]
Text = Annotated[str, Field(max_length=5_000)]


class Location(ApiModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class MonthlyCharge(ApiModel):
    type: Literal["monthly"]
    kind: ChargeKind
    label: str = Field(max_length=LABEL_MAX_LENGTH)
    amount_paise: Paise


class MeteredCharge(ApiModel):
    type: Literal["metered"]
    kind: ChargeKind
    label: str = Field(max_length=LABEL_MAX_LENGTH)
    rate_paise: Paise
    unit: str = Field(max_length=UNIT_MAX_LENGTH)
    monthly_estimate_paise: Paise


class OneTimeCharge(ApiModel):
    type: Literal["oneTime"]
    kind: ChargeKind
    label: str = Field(max_length=LABEL_MAX_LENGTH)
    amount_paise: Paise


Charge = Annotated[MonthlyCharge | MeteredCharge | OneTimeCharge, Field(discriminator="type")]


# Owners.


class OwnerCreate(ApiModel):
    phone: str = Field(max_length=20)
    legal_name: str = Field(max_length=200)
    business_name: str = Field(max_length=200)
    gstin: str | None = Field(default=None, max_length=20)
    # The owner's own name, for their account; kept only if the account has none yet.
    name: str | None = Field(default=None, max_length=200)


class OwnerInfo(ApiModel):
    id: uuid.UUID
    legal_name: str
    business_name: str
    gstin: str | None
    kyc_status: KycStatus
    status: OwnerStatus
    # Staff see the owner's phone in full.
    phone: str | None
    name: str | None


class OwnerPage(ApiModel):
    items: list[OwnerInfo]
    next_cursor: uuid.UUID | None


# Listings.


class PropertyCreate(ApiModel):
    owner: uuid.UUID
    # The locality's slug (GET /v1/localities).
    locality: str = Field(max_length=64)
    name: str = Field(max_length=200)
    address_line: str = Field(max_length=500)
    location: Location
    location_precision: LocationPrecision
    gender_policy: GenderPolicy
    meals: Meals
    description: Text = ""
    house_rules: list[Annotated[str, Field(max_length=300)]] = Field(default=[], max_length=40)
    licence_status: LicenceStatus = LicenceStatus.UNKNOWN
    licence_number: str | None = Field(default=None, max_length=100)
    society_permission: SocietyPermission = SocietyPermission.NOT_APPLICABLE
    instant_confirm: bool = False


class PropertyUpdate(ApiModel):
    """Only the fields sent change; ``licenceNumber: null`` clears it."""

    name: str | None = Field(default=None, max_length=200)
    address_line: str | None = Field(default=None, max_length=500)
    location: Location | None = None
    location_precision: LocationPrecision | None = None
    gender_policy: GenderPolicy | None = None
    meals: Meals | None = None
    description: Text | None = None
    house_rules: list[Annotated[str, Field(max_length=300)]] | None = Field(
        default=None, max_length=40
    )
    licence_status: LicenceStatus | None = None
    licence_number: str | None = Field(default=None, max_length=100)
    society_permission: SocietyPermission | None = None
    instant_confirm: bool | None = None


class StatusChange(ApiModel):
    status: PropertyStatus


class AmenitiesChange(ApiModel):
    amenities: list[Annotated[str, Field(max_length=64)]] = Field(max_length=60)


class MediaChange(ApiModel):
    """The listing's photos and videos, in order: the first is the cover."""

    media: list[uuid.UUID] = Field(max_length=40)


# Room categories, rooms and beds.


class CategoryCreate(ApiModel):
    occupancy: Occupancy
    label: str = Field(max_length=200)
    base_rent_paise: Paise
    security_deposit_paise: Paise
    ac: bool = False
    attached_bath: bool = False
    balcony: bool = False
    owner_min_rent_paise: Paise | None = None
    owner_max_rent_paise: Paise | None = None
    mandatory_charges: list[Charge] = Field(default=[], max_length=20)


class CategoryUpdate(ApiModel):
    """Only the fields sent change; null clears the owner's minimum or maximum."""

    label: str | None = Field(default=None, max_length=200)
    base_rent_paise: Paise | None = None
    security_deposit_paise: Paise | None = None
    ac: bool | None = None
    attached_bath: bool | None = None
    balcony: bool | None = None
    owner_min_rent_paise: Paise | None = None
    owner_max_rent_paise: Paise | None = None
    mandatory_charges: list[Charge] | None = Field(default=None, max_length=20)
    status: CategoryStatus | None = None


class RoomCreate(ApiModel):
    label: str = Field(max_length=100)
    floor: int | None = Field(default=None, ge=-10, le=200)
    # Beds made with the room, labelled A, B, ...: at most the occupancy.
    beds: int = Field(default=0, ge=0, le=4)


class BedCreate(ApiModel):
    label: str = Field(max_length=100)


class BedUpdate(ApiModel):
    status: BedStatus


class BedInfo(ApiModel):
    id: uuid.UUID
    label: str
    status: BedStatus


class RoomInfo(ApiModel):
    id: uuid.UUID
    label: str
    floor: int | None
    beds: list[BedInfo]


class CategoryInfo(ApiModel):
    id: uuid.UUID
    occupancy: Occupancy
    label: str
    ac: bool
    attached_bath: bool
    balcony: bool
    base_rent_paise: int
    owner_min_rent_paise: int | None
    owner_max_rent_paise: int | None
    security_deposit_paise: int
    mandatory_charges: list[Charge]
    # What the charges come to each month (metered ones at their estimate), and once.
    monthly_charges_paise: int
    one_time_charges_paise: int
    status: CategoryStatus
    rooms: list[RoomInfo]


class Rendition(ApiModel):
    name: str
    content_type: str
    url: str
    width: int | None
    height: int | None


class ListingMedia(ApiModel):
    id: uuid.UUID
    purpose: str
    status: str
    content_type: str
    verified_capture: bool
    captured_at: datetime | None
    renditions: list[Rendition]


class LocalityInfo(ApiModel):
    slug: str
    name: str


class ListingInfo(ApiModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str
    address_line: str
    location: Location
    display_location: Location
    location_precision: LocationPrecision
    gender_policy: GenderPolicy
    meals: Meals
    house_rules: list[str]
    verification_status: VerificationStatus
    licence_status: LicenceStatus
    licence_number: str | None
    society_permission: SocietyPermission
    instant_confirm: bool
    status: PropertyStatus
    published_at: datetime | None
    owner: OwnerInfo
    locality: LocalityInfo
    amenities: list[str]
    categories: list[CategoryInfo]
    media: list[ListingMedia]
    # What stops it being published now; empty when nothing does.
    problems: list[str]


class ListingCreated(ListingInfo):
    # Listings whose exact pin is within 30 m: likely the same building, listed twice.
    possible_duplicates: list[uuid.UUID]


class ListingSummary(ApiModel):
    id: uuid.UUID
    slug: str
    name: str
    locality: LocalityInfo
    status: PropertyStatus
    verification_status: VerificationStatus
    updated_at: datetime
    cover: ListingMedia | None


class ListingPage(ApiModel):
    items: list[ListingSummary]
    next_cursor: uuid.UUID | None


class HistoryEntry(ApiModel):
    occurred_at: datetime
    action: str
    entity_type: str
    entity_id: str
    actor_type: str
    details: dict[str, object]


class History(ApiModel):
    items: list[HistoryEntry]


class AmenityInfo(ApiModel):
    slug: str
    name: str


class AmenityList(ApiModel):
    items: list[AmenityInfo]
