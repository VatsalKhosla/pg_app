"""Catalog requests and responses (ARCHITECTURE §15). Money is integer paise in fields ending in
``Paise``. These are staff views: the exact location and the address appear here, never in a
public response."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field

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
from app.modules.catalog.domain.verification import (
    LICENCE_NUMBER_MAX_LENGTH,
    MAX_PHOTOS,
    MIN_PHOTOS,
    MOST_EXITS,
    NOTES_MAX_LENGTH,
    OLDEST_BUILDING_YEARS,
    REASON_MAX_LENGTH,
    Condition,
    Cracks,
    VisitResult,
    VisitStatus,
    WomenSafety,
)

Paise = Annotated[int, Field(ge=0)]
Text = Annotated[str, Field(max_length=5_000)]


class LatLng(ApiModel):
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


class OwnerUpdate(ApiModel):
    """Only the fields sent change; ``gstin: null`` clears it."""

    legal_name: str | None = Field(default=None, max_length=200)
    business_name: str | None = Field(default=None, max_length=200)
    gstin: str | None = Field(default=None, max_length=20)


class OwnerInfo(ApiModel):
    id: uuid.UUID
    legal_name: str
    business_name: str
    gstin: str | None
    kyc_status: KycStatus
    status: OwnerStatus
    # Staff, and the owner, see the owner's phone in full.
    phone: str | None
    name: str | None
    # The owner agreement's version they accepted last, and whether that is the current one
    # (ADR 0025): a new version asks them to accept again.
    agreement_version: str | None
    agreement_current: bool


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
    location: LatLng
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
    location: LatLng | None = None
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
    # How many beds each of its rooms can hold: its occupancy as a number.
    beds_per_room: int
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


class ListingLocality(ApiModel):
    slug: str
    name: str


class ListingInfo(ApiModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str
    address_line: str
    location: LatLng
    display_location: LatLng
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
    # The statuses it can move to from this one (POST .../status).
    next_statuses: list[PropertyStatus]
    # Whether a verification visit can be booked for it now, and whether its verification can be
    # suspended (ADR 0024).
    can_book_visit: bool
    can_suspend: bool
    published_at: datetime | None
    owner: OwnerInfo
    locality: ListingLocality
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
    locality: ListingLocality
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


# What anyone may see (step 2.7, ADR 0026): nothing here is private.


class PublicCategory(ApiModel):
    id: uuid.UUID
    occupancy: Occupancy
    label: str
    ac: bool
    attached_bath: bool
    balcony: bool
    base_rent_paise: int
    security_deposit_paise: int
    mandatory_charges: list[Charge]
    # What the charges come to each month (metered ones at their estimate), and once.
    monthly_charges_paise: int
    one_time_charges_paise: int


class PublicMedia(ApiModel):
    id: uuid.UUID
    content_type: str
    # Taken on site by our field agent (ADR 0022): shown as a verified photo.
    verified_capture: bool
    renditions: list[Rendition]


class SafetySummary(ApiModel):
    """What the field agent found on their last visit that passed the building (ADR 0024)."""

    verified_on: date
    # Separate ways out of the building.
    exits: int
    fire_extinguishers: bool
    cctv: bool
    # Someone in charge on site at night.
    warden: bool
    women_safety: list[WomenSafety]


class PlaceNearby(ApiModel):
    slug: str
    name: str
    # From the display point.
    distance_m: int


class PublicListing(ApiModel):
    """A live listing as anyone sees it. Its location is the display point, 80 to 150 m from the
    building; the address, the exact point and the owner's phone come only from .../contact."""

    id: uuid.UUID
    slug: str
    name: str
    description: str
    locality: ListingLocality
    display_location: LatLng
    gender_policy: GenderPolicy
    meals: Meals
    house_rules: list[str]
    # A field agent's visit passed (ADR 0024), and what they found; null before one has.
    verified: bool
    safety: SafetySummary | None
    licence_status: LicenceStatus
    society_permission: SocietyPermission
    # Campuses within 5 km and the two nearest metro stations, nearest first.
    campuses_nearby: list[PlaceNearby]
    stations_nearby: list[PlaceNearby]
    owner_business_name: str
    amenities: list[AmenityInfo]
    # Active categories with a bed to sell.
    categories: list[PublicCategory]
    media: list[PublicMedia]


class ListingContact(ApiModel):
    """The owner's phone, the address and the exact point, for someone allowed to see them."""

    owner_phone: str | None
    address_line: str
    location: LatLng
    location_precision: LocationPrecision


# Verification visits (ADR 0024).


class AgentInfo(ApiModel):
    id: uuid.UUID
    name: str | None


class FieldAgentList(ApiModel):
    items: list[AgentInfo]


class VisitCreate(ApiModel):
    # A field agent (GET /v1/ops/field-agents).
    agent: uuid.UUID
    # With its offset, so there is no doubt about the time zone.
    scheduled_for: AwareDatetime


class Reason(ApiModel):
    reason: str = Field(min_length=1, max_length=REASON_MAX_LENGTH)


class VisitChecklist(ApiModel):
    """The agent's answers on site. Every field is required, so nothing is assumed."""

    # As the owner or a document says; null if nobody knows.
    building_age_years: int | None = Field(ge=0, le=OLDEST_BUILDING_YEARS)
    condition: Condition
    cracks: Cracks
    exits: int = Field(ge=0, le=MOST_EXITS)
    fire_extinguishers: bool
    cctv: bool
    warden: bool
    women_safety: list[WomenSafety] = Field(max_length=len(WomenSafety))
    # As shown on the licence on site; null if there is none to see.
    licence_number: str | None = Field(max_length=LICENCE_NUMBER_MAX_LENGTH)
    society_permission: SocietyPermission
    # A sealing, demolition or unsafe-building notice from the authorities: the visit can't pass.
    authority_notice: bool


class ReportSubmit(ApiModel):
    checklist: VisitChecklist
    result: VisitResult
    # Required when the visit failed.
    notes: str = Field(default="", max_length=NOTES_MAX_LENGTH)
    # Where the agent's phone says they are, and how sure it is (metres).
    position: LatLng
    accuracy_m: float = Field(ge=0, le=10_000)
    # Verification photos the agent uploaded (purpose verification_photo), in order.
    photos: list[uuid.UUID] = Field(min_length=MIN_PHOTOS, max_length=MAX_PHOTOS)
    # Make the agent's position the building's pin; a new public point follows.
    move_pin: bool = False


class VisitPlace(ApiModel):
    """The property, as the agent needs it to get there: staff see the address and the pin."""

    id: uuid.UUID
    name: str
    address_line: str
    location: LatLng
    locality: ListingLocality
    owner_business_name: str
    owner_phone: str | None
    verification_status: VerificationStatus
    status: PropertyStatus


class VisitInfo(ApiModel):
    id: uuid.UUID
    status: VisitStatus
    scheduled_for: datetime
    agent: AgentInfo | None
    property: VisitPlace
    # The report, once in: when (the server's clock), where the agent was, how far that was from
    # the pin, the answers, and private photos behind links signed for five minutes.
    submitted_at: datetime | None
    result: VisitResult | None
    notes: str
    position: LatLng | None
    accuracy_m: int | None
    distance_m: int | None
    checklist: VisitChecklist | None
    photos: list[ListingMedia]
    cancelled_at: datetime | None
    cancel_reason: str | None


class VisitPage(ApiModel):
    items: list[VisitInfo]
    next_cursor: uuid.UUID | None


# The owner agreement (ADR 0025).


class AgreementInfo(ApiModel):
    version: str
    # Markdown: headings, paragraphs and lists.
    text: str
    # What an acceptance must name: the hash of exactly this text.
    document_sha256: str
    # Whether this owner has accepted this version, and when; and the version they accepted last.
    accepted: bool
    accepted_at: datetime | None
    accepted_version: str | None


class AcceptanceCreate(ApiModel):
    """The version and text the owner was shown; anything else is refused (409
    AGREEMENT_CHANGED)."""

    version: str = Field(max_length=64)
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class AcceptanceInfo(ApiModel):
    version: str
    document_sha256: str
    accepted_at: datetime
    ip: str
    user_agent: str | None


class AcceptanceList(ApiModel):
    items: list[AcceptanceInfo]
