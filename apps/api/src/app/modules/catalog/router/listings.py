"""Catalog routes (ARCHITECTURE §15, ADR 0023): the ops console's listings, and the amenities
anyone may list.

Every /v1/ops route is for ops and admins in a staff session (403 for anyone else signed in).
Every change answers with the whole listing as it now stands, so the console never shows a stale
one.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, status

from app.core.clock import ClockDep
from app.core.current_actor import CurrentActor
from app.core.db import DbSession
from app.core.errors import ForbiddenError
from app.core.geometry import Point
from app.core.money import Paise
from app.core.pagination import PageParams
from app.modules.catalog.domain.charges import (
    MandatoryCharge,
    monthly_total,
    one_time_total,
)
from app.modules.catalog.domain.charges import MeteredCharge as MeteredChargeRule
from app.modules.catalog.domain.charges import MonthlyCharge as MonthlyChargeRule
from app.modules.catalog.domain.charges import OneTimeCharge as OneTimeChargeRule
from app.modules.catalog.domain.listing import (
    GenderPolicy,
    LicenceStatus,
    LocationPrecision,
    Meals,
    PropertyStatus,
    SocietyPermission,
    VerificationStatus,
    next_statuses,
)
from app.modules.catalog.domain.owners import KycStatus, OwnerStatus
from app.modules.catalog.domain.rooms import BEDS_PER_ROOM, BedStatus, CategoryStatus, Occupancy
from app.modules.catalog.domain.verification import can_schedule, can_suspend
from app.modules.catalog.policies import can_manage_listings
from app.modules.catalog.schemas import (
    AmenitiesChange,
    AmenityInfo,
    AmenityList,
    BedCreate,
    BedInfo,
    BedUpdate,
    CategoryCreate,
    CategoryInfo,
    CategoryUpdate,
    Charge,
    History,
    HistoryEntry,
    LatLng,
    ListingCreated,
    ListingInfo,
    ListingLocality,
    ListingMedia,
    ListingPage,
    ListingSummary,
    MediaChange,
    MeteredCharge,
    MonthlyCharge,
    OneTimeCharge,
    OwnerCreate,
    OwnerInfo,
    OwnerPage,
    PropertyCreate,
    PropertyUpdate,
    Rendition,
    RoomCreate,
    RoomInfo,
    StatusChange,
)
from app.modules.catalog.service import (
    CatalogReader,
    CategoryChanges,
    CategoryDraft,
    InventoryService,
    ListingDetail,
    ListingService,
    OwnerRecord,
    OwnerService,
    PropertyChanges,
    PropertyDraft,
)
from app.modules.media.service import MediaRef

router = APIRouter(prefix="/v1", tags=["catalog"])

SearchText = Annotated[str | None, Query(max_length=100, description="Part of a name, or a phone")]


def require_listing_staff(actor: CurrentActor) -> None:
    if not can_manage_listings(actor):
        raise ForbiddenError


def catalog_reader(request: Request, db: DbSession) -> CatalogReader:
    return CatalogReader(db, buckets=request.app.state.media_buckets, flags=request.app.state.flags)


def _listings(request: Request, db: DbSession, clock: ClockDep) -> ListingService:
    return ListingService(
        db, clock, buckets=request.app.state.media_buckets, flags=request.app.state.flags
    )


# Charges: the API's shapes and the domain's.


def _charge_in(charge: Charge) -> MandatoryCharge:
    match charge:
        case MonthlyCharge():
            return MonthlyChargeRule(charge.kind, charge.label, Paise(charge.amount_paise))
        case MeteredCharge():
            return MeteredChargeRule(
                charge.kind,
                charge.label,
                rate=Paise(charge.rate_paise),
                unit=charge.unit,
                monthly_estimate=Paise(charge.monthly_estimate_paise),
            )
        case OneTimeCharge():
            return OneTimeChargeRule(charge.kind, charge.label, Paise(charge.amount_paise))


def _charge_out(charge: MandatoryCharge) -> Charge:
    match charge:
        case MonthlyChargeRule():
            return MonthlyCharge(
                type="monthly", kind=charge.kind, label=charge.label, amount_paise=charge.amount
            )
        case MeteredChargeRule():
            return MeteredCharge(
                type="metered",
                kind=charge.kind,
                label=charge.label,
                rate_paise=charge.rate,
                unit=charge.unit,
                monthly_estimate_paise=charge.monthly_estimate,
            )
        case OneTimeChargeRule():
            return OneTimeCharge(
                type="oneTime", kind=charge.kind, label=charge.label, amount_paise=charge.amount
            )


# Responses.


def _owner(record: OwnerRecord) -> OwnerInfo:
    owner, account = record.owner, record.account
    return OwnerInfo(
        id=owner.public_id,
        legal_name=owner.legal_name,
        business_name=owner.business_name,
        gstin=owner.gstin,
        kyc_status=KycStatus(owner.kyc_status),
        status=OwnerStatus(owner.status),
        phone=None if account is None else account.phone_e164,
        name=None if account is None else account.name,
    )


def media_info(ref: MediaRef) -> ListingMedia:
    return ListingMedia(
        id=ref.public_id,
        purpose=ref.purpose,
        status=ref.status,
        content_type=ref.content_type,
        verified_capture=ref.verified_capture,
        captured_at=ref.captured_at,
        renditions=[
            Rendition(
                name=rendition.name,
                content_type=rendition.content_type,
                url=rendition.url,
                width=rendition.width,
                height=rendition.height,
            )
            for rendition in ref.renditions
        ],
    )


def lat_lng(point: Point) -> LatLng:
    return LatLng(lat=point.lat, lng=point.lng)


def _listing(detail: ListingDetail) -> ListingInfo:
    found = detail.property
    return ListingInfo(
        id=found.public_id,
        slug=found.slug,
        name=found.name,
        description=found.description,
        address_line=found.address_line,
        location=lat_lng(detail.exact),
        display_location=lat_lng(detail.display),
        location_precision=LocationPrecision(found.location_precision),
        gender_policy=GenderPolicy(found.gender_policy),
        meals=Meals(found.meals),
        house_rules=list(found.house_rules),
        verification_status=VerificationStatus(found.verification_status),
        licence_status=LicenceStatus(found.licence_status),
        licence_number=found.licence_number,
        society_permission=SocietyPermission(found.society_permission),
        instant_confirm=found.instant_confirm,
        status=PropertyStatus(found.status),
        next_statuses=next_statuses(PropertyStatus(found.status)),
        can_book_visit=can_schedule(VerificationStatus(found.verification_status)),
        can_suspend=can_suspend(VerificationStatus(found.verification_status)),
        published_at=found.published_at,
        owner=_owner(detail.owner),
        locality=ListingLocality(slug=detail.locality.slug, name=detail.locality.name),
        amenities=list(detail.amenities),
        categories=[
            CategoryInfo(
                id=view.category.public_id,
                occupancy=Occupancy(view.category.occupancy),
                label=view.category.label,
                ac=view.category.ac,
                attached_bath=view.category.attached_bath,
                balcony=view.category.balcony,
                base_rent_paise=view.category.base_rent_paise,
                owner_min_rent_paise=view.category.owner_min_rent_paise,
                owner_max_rent_paise=view.category.owner_max_rent_paise,
                security_deposit_paise=view.category.security_deposit_paise,
                beds_per_room=BEDS_PER_ROOM[Occupancy(view.category.occupancy)],
                mandatory_charges=[_charge_out(charge) for charge in view.charges],
                monthly_charges_paise=monthly_total(view.charges),
                one_time_charges_paise=one_time_total(view.charges),
                status=CategoryStatus(view.category.status),
                rooms=[
                    RoomInfo(
                        id=room.room.public_id,
                        label=room.room.label,
                        floor=room.room.floor,
                        beds=[
                            BedInfo(id=bed.public_id, label=bed.label, status=BedStatus(bed.status))
                            for bed in room.beds
                        ],
                    )
                    for room in view.rooms
                ],
            )
            for view in detail.categories
        ],
        media=[media_info(ref) for ref in detail.media],
        problems=list(detail.problems),
    )


async def current_listing(request: Request, db: DbSession, property_id: uuid.UUID) -> ListingInfo:
    return _listing(await catalog_reader(request, db).listing(property_id))


# Public.


@router.get("/amenities", summary="The amenities a listing can have")
async def amenities(request: Request, response: Response, db: DbSession) -> AmenityList:
    response.headers["Cache-Control"] = "public, max-age=3600"
    found = await catalog_reader(request, db).amenities()
    return AmenityList(items=[AmenityInfo(slug=item.slug, name=item.name) for item in found])


# Owners.


@router.get("/ops/owners", summary="Owners, to choose one for a listing")
async def owners(
    actor: CurrentActor,
    page: PageParams,
    db: DbSession,
    clock: ClockDep,
    q: SearchText = None,
) -> OwnerPage:
    """By phone number (exactly) or by name (any part)."""
    require_listing_staff(actor)
    found, next_cursor = await OwnerService(db, clock).page(page, text=q)
    return OwnerPage(items=[_owner(record) for record in found], next_cursor=next_cursor)


@router.post("/ops/owners", status_code=status.HTTP_201_CREATED, summary="Add an owner")
async def add_owner(
    body: OwnerCreate, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> OwnerInfo:
    """Makes the owner's account from their phone if they haven't signed in yet."""
    require_listing_staff(actor)
    record = await OwnerService(db, clock).add(
        actor,
        phone=body.phone,
        legal_name=body.legal_name,
        business_name=body.business_name,
        gstin=body.gstin,
        name=body.name,
    )
    return _owner(record)


# Listings.


@router.get("/ops/properties", summary="Listings")
async def listings(
    request: Request,
    actor: CurrentActor,
    *,
    page: PageParams,
    db: DbSession,
    q: SearchText = None,
    listing_status: Annotated[PropertyStatus | None, Query(alias="status")] = None,
) -> ListingPage:
    require_listing_staff(actor)
    found, next_cursor = await catalog_reader(request, db).listings(
        page, status=listing_status, text=q
    )
    return ListingPage(
        items=[
            ListingSummary(
                id=item.property.public_id,
                slug=item.property.slug,
                name=item.property.name,
                locality=ListingLocality(slug=item.locality.slug, name=item.locality.name),
                status=PropertyStatus(item.property.status),
                verification_status=VerificationStatus(item.property.verification_status),
                updated_at=item.property.updated_at,
                cover=None if item.cover is None else media_info(item.cover),
            )
            for item in found
        ],
        next_cursor=next_cursor,
    )


@router.post(
    "/ops/properties", status_code=status.HTTP_201_CREATED, summary="Start a listing (a draft)"
)
async def create_listing(
    body: PropertyCreate, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> ListingCreated:
    """Answers with any listing whose pin is within 30 m, which may be the same building."""
    require_listing_staff(actor)
    created = await _listings(request, db, clock).create_property(
        actor,
        PropertyDraft(
            owner=body.owner,
            locality=body.locality,
            name=body.name,
            address_line=body.address_line,
            location=Point(lat=body.location.lat, lng=body.location.lng),
            location_precision=body.location_precision,
            gender_policy=body.gender_policy,
            meals=body.meals,
            description=body.description,
            house_rules=tuple(body.house_rules),
            licence_status=body.licence_status,
            licence_number=body.licence_number,
            society_permission=body.society_permission,
            instant_confirm=body.instant_confirm,
        ),
    )
    reader = catalog_reader(request, db)
    listing = _listing(await reader.listing(created.public_id))
    duplicates = await reader.duplicates_of(created.public_id)
    return ListingCreated(**dict(listing), possible_duplicates=duplicates)


@router.get("/ops/properties/{property_id}", summary="A listing in full")
async def listing(
    property_id: uuid.UUID, request: Request, actor: CurrentActor, db: DbSession
) -> ListingInfo:
    require_listing_staff(actor)
    return await current_listing(request, db, property_id)


@router.patch("/ops/properties/{property_id}", summary="Change a listing's details")
async def update_listing(
    property_id: uuid.UUID,
    body: PropertyUpdate,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> ListingInfo:
    """Only the fields sent change. Moving the pin makes a new display point."""
    require_listing_staff(actor)
    sent = body.model_dump(include=body.model_fields_set, by_alias=False)
    changes: PropertyChanges = {}
    for name in ("name", "address_line", "description", "licence_number"):
        if name in sent:
            changes[name] = sent[name]
    for name in (
        "location_precision",
        "gender_policy",
        "meals",
        "licence_status",
        "society_permission",
        "instant_confirm",
    ):
        if sent.get(name) is not None:
            changes[name] = getattr(body, name)  # type: ignore[literal-required]
    if body.house_rules is not None:
        changes["house_rules"] = tuple(body.house_rules)
    if body.location is not None:
        changes["location"] = Point(lat=body.location.lat, lng=body.location.lng)
    await _listings(request, db, clock).update_property(actor, property_id, changes)
    return await current_listing(request, db, property_id)


@router.post("/ops/properties/{property_id}/status", summary="Publish, pause, delist or relist")
async def change_status(
    property_id: uuid.UUID,
    body: StatusChange,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> ListingInfo:
    """Publishing needs a room category with a bed to sell (409 LISTING_INCOMPLETE)."""
    require_listing_staff(actor)
    await _listings(request, db, clock).move(actor, property_id, body.status)
    return await current_listing(request, db, property_id)


@router.put("/ops/properties/{property_id}/amenities", summary="Set a listing's amenities")
async def set_amenities(
    property_id: uuid.UUID,
    body: AmenitiesChange,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> ListingInfo:
    require_listing_staff(actor)
    await _listings(request, db, clock).set_amenities(actor, property_id, body.amenities)
    return await current_listing(request, db, property_id)


@router.put("/ops/properties/{property_id}/media", summary="Set a listing's photos and videos")
async def set_media(
    property_id: uuid.UUID,
    body: MediaChange,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> ListingInfo:
    """In page order, the first being the cover; uploads come from POST /v1/media."""
    require_listing_staff(actor)
    await _listings(request, db, clock).set_media(actor, property_id, body.media)
    return await current_listing(request, db, property_id)


@router.get("/ops/properties/{property_id}/history", summary="Everything done to a listing")
async def history(
    property_id: uuid.UUID, request: Request, actor: CurrentActor, db: DbSession
) -> History:
    """From the audit log, newest first: the listing, its rooms and its beds."""
    require_listing_staff(actor)
    entries = await catalog_reader(request, db).history(property_id)
    return History(
        items=[
            HistoryEntry(
                occurred_at=entry.occurred_at,
                action=entry.action,
                entity_type=entry.entity_type,
                entity_id=entry.entity_id,
                actor_type=entry.actor_type,
                details=entry.details,
            )
            for entry in entries
        ]
    )


# Room categories, rooms and beds.


@router.post(
    "/ops/properties/{property_id}/room-categories",
    status_code=status.HTTP_201_CREATED,
    summary="Add a room category",
)
async def add_room_category(
    property_id: uuid.UUID,
    body: CategoryCreate,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> ListingInfo:
    require_listing_staff(actor)
    await InventoryService(db, clock).add_room_category(
        actor,
        property_id,
        CategoryDraft(
            occupancy=body.occupancy,
            label=body.label,
            base_rent=Paise(body.base_rent_paise),
            security_deposit=Paise(body.security_deposit_paise),
            ac=body.ac,
            attached_bath=body.attached_bath,
            balcony=body.balcony,
            owner_min_rent=None
            if body.owner_min_rent_paise is None
            else Paise(body.owner_min_rent_paise),
            owner_max_rent=None
            if body.owner_max_rent_paise is None
            else Paise(body.owner_max_rent_paise),
            mandatory_charges=tuple(_charge_in(charge) for charge in body.mandatory_charges),
        ),
    )
    return await current_listing(request, db, property_id)


@router.patch("/ops/room-categories/{category_id}", summary="Change a room category")
async def update_room_category(
    category_id: uuid.UUID,
    body: CategoryUpdate,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> ListingInfo:
    """Only the fields sent change; null clears the owner's minimum or maximum."""
    require_listing_staff(actor)
    sent = body.model_fields_set
    changes: CategoryChanges = {}
    if body.label is not None:
        changes["label"] = body.label
    for name in ("ac", "attached_bath", "balcony", "status"):
        if getattr(body, name) is not None:
            changes[name] = getattr(body, name)
    if body.base_rent_paise is not None:
        changes["base_rent"] = Paise(body.base_rent_paise)
    if body.security_deposit_paise is not None:
        changes["security_deposit"] = Paise(body.security_deposit_paise)
    if "owner_min_rent_paise" in sent:
        low = body.owner_min_rent_paise
        changes["owner_min_rent"] = None if low is None else Paise(low)
    if "owner_max_rent_paise" in sent:
        high = body.owner_max_rent_paise
        changes["owner_max_rent"] = None if high is None else Paise(high)
    if body.mandatory_charges is not None:
        changes["mandatory_charges"] = tuple(
            _charge_in(charge) for charge in body.mandatory_charges
        )
    await InventoryService(db, clock).update_room_category(actor, category_id, changes)
    return await current_listing(
        request, db, await catalog_reader(request, db).listing_of(category=category_id)
    )


@router.post(
    "/ops/room-categories/{category_id}/rooms",
    status_code=status.HTTP_201_CREATED,
    summary="Add a room, with its beds",
)
async def add_room(
    category_id: uuid.UUID,
    body: RoomCreate,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> ListingInfo:
    require_listing_staff(actor)
    await InventoryService(db, clock).add_room(
        actor, category_id, label=body.label, floor=body.floor, beds=body.beds
    )
    return await current_listing(
        request, db, await catalog_reader(request, db).listing_of(category=category_id)
    )


@router.post("/ops/rooms/{room_id}/beds", status_code=status.HTTP_201_CREATED, summary="Add a bed")
async def add_bed(
    room_id: uuid.UUID,
    body: BedCreate,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> ListingInfo:
    """409 ROOM_FULL once the room has as many beds as its occupancy."""
    require_listing_staff(actor)
    await InventoryService(db, clock).add_bed(actor, room_id, label=body.label)
    return await current_listing(
        request, db, await catalog_reader(request, db).listing_of(room=room_id)
    )


@router.patch("/ops/beds/{bed_id}", summary="Take a bed out of what can be sold, or back")
async def update_bed(
    bed_id: uuid.UUID,
    body: BedUpdate,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> ListingInfo:
    require_listing_staff(actor)
    await InventoryService(db, clock).set_bed_status(actor, bed_id, body.status)
    return await current_listing(
        request, db, await catalog_reader(request, db).listing_of(bed=bed_id)
    )
