"""Public catalog routes (ARCHITECTURE §10.5, §15; ADR 0026): a live listing, as anyone sees it,
and its contact details for someone signed in and allowed to see them."""

from typing import Annotated, Final

from fastapi import APIRouter, Path, Request, Response

from app.core.clock import ClockDep
from app.core.current_actor import CurrentActor
from app.core.db import DbSession
from app.modules.catalog.domain.charges import monthly_total, one_time_total
from app.modules.catalog.domain.listing import SLUG_MAX_LENGTH
from app.modules.catalog.router.listings import charge_info, lat_lng, renditions
from app.modules.catalog.schemas import (
    AmenityInfo,
    LatLng,
    ListingContact,
    ListingLocality,
    PublicCategory,
    PublicListing,
    PublicMedia,
)
from app.modules.catalog.service.public import PublicCatalog

router = APIRouter(prefix="/v1", tags=["catalog"])

# A listing changes when ops edit it; a minute's caching keeps the page fresh enough.
CACHE_CONTROL: Final = "public, max-age=60"
Slug = Annotated[str, Path(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=SLUG_MAX_LENGTH)]


def _public(request: Request, db: DbSession, clock: ClockDep) -> PublicCatalog:
    state = request.app.state
    return PublicCatalog(
        db,
        clock,
        buckets=state.media_buckets,
        flags=state.flags,
        access=state.contact_access,
        limiter=state.rate_limiter,
    )


@router.get("/properties/{slug}", summary="A live listing, as anyone sees it")
async def public_listing(
    slug: Slug, request: Request, response: Response, db: DbSession, clock: ClockDep
) -> PublicListing:
    """Its location is the display point, 80 to 150 m from the building. Anything not live, or
    not verified while only verified PGs are shown, answers 404."""
    found = await _public(request, db, clock).listing(slug)
    response.headers["Cache-Control"] = CACHE_CONTROL
    return PublicListing(
        id=found.public_id,
        slug=found.slug,
        name=found.name,
        description=found.description,
        locality=ListingLocality(slug=found.locality.slug, name=found.locality.name),
        display_location=LatLng(lat=found.display.lat, lng=found.display.lng),
        gender_policy=found.gender_policy,
        meals=found.meals,
        house_rules=list(found.house_rules),
        verified=found.verified,
        owner_business_name=found.owner_business_name,
        amenities=[AmenityInfo(slug=item.slug, name=item.name) for item in found.amenities],
        categories=[
            PublicCategory(
                id=category.public_id,
                occupancy=category.occupancy,
                label=category.label,
                ac=category.ac,
                attached_bath=category.attached_bath,
                balcony=category.balcony,
                base_rent_paise=category.base_rent,
                security_deposit_paise=category.security_deposit,
                mandatory_charges=[charge_info(charge) for charge in category.charges],
                monthly_charges_paise=monthly_total(category.charges),
                one_time_charges_paise=one_time_total(category.charges),
            )
            for category in found.categories
        ],
        media=[
            PublicMedia(
                id=ref.public_id,
                content_type=ref.content_type,
                verified_capture=ref.verified_capture,
                renditions=renditions(ref),
            )
            for ref in found.media
        ],
    )


@router.get("/properties/{slug}/contact", summary="The owner's phone and the exact address")
async def listing_contact(
    slug: Slug, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> ListingContact:
    """For someone signed in, while ``hide_owner_contact`` is off or once they have a visit
    scheduled or a booking confirmed there; otherwise 403 CONTACT_HIDDEN. Each answer is
    audited."""
    found = await _public(request, db, clock).contact(actor, slug)
    return ListingContact(
        owner_phone=found.phone,
        address_line=found.address_line,
        location=lat_lng(found.exact),
        location_precision=found.location_precision,
    )
