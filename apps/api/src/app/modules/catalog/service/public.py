"""What anyone may see of the catalog (step 2.7, ADR 0026): a live listing by its slug, with its
display point, and never its exact point, its address or the owner's phone. Those details come
from ``contact``, for someone signed in, when ``hide_owner_contact`` allows it.

The public read never loads what it mustn't show: it asks for the display point alone and for
the owner's business name, so a mistake in a response can't leak the rest.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Final

from app.core import audit
from app.core.calendar import india_date
from app.core.errors import NotFoundError
from app.core.flags import Flag
from app.core.money import Paise
from app.core.ratelimit import RateLimit, enforce
from app.modules.catalog.domain.listing import (
    GenderPolicy,
    LicenceStatus,
    LocationPrecision,
    Meals,
    PropertyStatus,
    SocietyPermission,
    VerificationStatus,
    is_public,
)
from app.modules.catalog.domain.privacy import contact_shown
from app.modules.catalog.domain.rooms import BedStatus, CategoryStatus, Occupancy
from app.modules.catalog.errors import ContactHiddenError
from app.modules.catalog.repository import (
    CatalogRepository,
    VisitRepository,
    charges_from_json,
    checklist_from_json,
)
from app.modules.geo.service import GeoLookup
from app.modules.identity.service import Accounts
from app.modules.media.domain.assets import AssetStatus, Moderation
from app.modules.media.service import MediaLookup

if TYPE_CHECKING:
    import uuid
    from datetime import date

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.core.flags import FlagReader
    from app.core.geometry import Point
    from app.core.ratelimit import RateLimiter
    from app.modules.catalog.contact import ContactAccess
    from app.modules.catalog.domain.charges import MandatoryCharge
    from app.modules.catalog.domain.verification import WomenSafety
    from app.modules.catalog.models import Amenity, Property, VerificationVisit
    from app.modules.geo.service import LocalityRef, PlaceNear
    from app.modules.media.service import Buckets, MediaRef

# What the page shows around a listing: campuses within walking or a short ride, and the two
# nearest metro stations.
CAMPUSES_WITHIN_M: Final = 5_000
NEARBY_CAMPUSES: Final = 3
NEARBY_STATIONS: Final = 2
# Looking up contact details, per person: plenty for anyone choosing a PG, too few to harvest
# owners' numbers. Let through while Redis is down, so a student on the way to a visit isn't
# stuck.
CONTACTS_PER_USER: Final = RateLimit("contacts-per-user", limit=30, window=timedelta(hours=1))


@dataclass(frozen=True, slots=True)
class PublicCategoryView:
    public_id: uuid.UUID
    occupancy: Occupancy
    label: str
    ac: bool
    attached_bath: bool
    balcony: bool
    base_rent: Paise
    security_deposit: Paise
    charges: tuple[MandatoryCharge, ...]


@dataclass(frozen=True, slots=True)
class SafetySummary:
    verified_on: date
    exits: int
    fire_extinguishers: bool
    cctv: bool
    warden: bool
    women_safety: tuple[WomenSafety, ...]


@dataclass(frozen=True, slots=True)
class PublicListingView:
    """A listing as anyone sees it. It holds nothing private, so nothing private can leave."""

    public_id: uuid.UUID
    slug: str
    name: str
    description: str
    gender_policy: GenderPolicy
    meals: Meals
    house_rules: tuple[str, ...]
    verified: bool
    # From the last visit that passed it; None before one has.
    safety: SafetySummary | None
    licence_status: LicenceStatus
    society_permission: SocietyPermission
    display: Point
    locality: LocalityRef
    # Nearest first, measured from the display point (ADR 0021).
    campuses: tuple[PlaceNear, ...]
    stations: tuple[PlaceNear, ...]
    owner_business_name: str
    # Active categories with a bed to sell, and approved media ready to show, in page order.
    categories: tuple[PublicCategoryView, ...]
    amenities: tuple[Amenity, ...]
    media: tuple[MediaRef, ...]


@dataclass(frozen=True, slots=True)
class ContactDetails:
    phone: str | None
    address_line: str
    exact: Point
    location_precision: LocationPrecision


def _safety(visit: VerificationVisit | None) -> SafetySummary | None:
    """The public part of the last passing report: what was there to keep people safe."""
    if visit is None or visit.checklist is None or visit.submitted_at is None:
        return None
    checklist = checklist_from_json(visit.checklist)
    return SafetySummary(
        verified_on=india_date(visit.submitted_at),
        exits=checklist.exits,
        fire_extinguishers=checklist.fire_extinguishers,
        cctv=checklist.cctv,
        warden=checklist.warden,
        women_safety=tuple(sorted(checklist.women_safety)),
    )


def _shown(ref: MediaRef) -> bool:
    return (
        ref.status is AssetStatus.READY
        and ref.moderation is Moderation.APPROVED
        and bool(ref.renditions)
    )


class PublicCatalog:
    def __init__(
        self,
        db: AsyncSession,
        clock: Clock,
        *,
        buckets: Buckets,
        flags: FlagReader,
        access: ContactAccess,
        limiter: RateLimiter,
    ) -> None:
        self._db = db
        self._clock = clock
        self._flags = flags
        self._access = access
        self._limiter = limiter
        self._catalog = CatalogRepository(db)
        self._visits = VisitRepository(db)
        self._geo = GeoLookup(db)
        # Without storage, so private files can't be signed for the public.
        self._media = MediaLookup(db, buckets)
        self._accounts = Accounts(db)

    async def _live(self, slug: str, *, verified_only: bool) -> Property:
        """The listing, if the public may see it; otherwise as if it didn't exist."""
        found = await self._catalog.property_by_slug(slug)
        if found is None or not is_public(
            PropertyStatus(found.status),
            VerificationStatus(found.verification_status),
            verified_only=verified_only,
        ):
            raise NotFoundError
        return found

    async def listing(self, slug: str) -> PublicListingView:
        verified_only = await self._flags.is_enabled(Flag.VERIFIED_ONLY)
        async with self._db.begin():
            found = await self._live(slug, verified_only=verified_only)
            display = await self._catalog.display_point(found.id)
            owner = (await self._catalog.owners_by_id([found.owner_id]))[found.owner_id]
            locality = (await self._geo.localities([found.locality_id]))[found.locality_id]
            categories = [
                category
                for category in await self._catalog.categories(found.id)
                if category.status == CategoryStatus.ACTIVE
            ]
            rooms = await self._catalog.rooms_of([category.id for category in categories])
            beds = await self._catalog.beds_of([room.id for room in rooms])
            amenities = await self._catalog.property_amenities(found.id)
            media_ids = (await self._catalog.media_of([found.id])).get(found.id, [])
            media = await self._media.by_id(media_ids)
            visit = await self._visits.latest_passed(found.id)
            campuses = await self._geo.campuses_near(
                display, within_m=CAMPUSES_WITHIN_M, limit=NEARBY_CAMPUSES
            )
            stations = await self._geo.stations_near(display, limit=NEARBY_STATIONS)
        rooms_with_beds = {bed.room_id for bed in beds if bed.status == BedStatus.ACTIVE}
        selling = {room.room_category_id for room in rooms if room.id in rooms_with_beds}
        return PublicListingView(
            public_id=found.public_id,
            slug=found.slug,
            name=found.name,
            description=found.description,
            gender_policy=GenderPolicy(found.gender_policy),
            meals=Meals(found.meals),
            house_rules=tuple(found.house_rules),
            verified=found.verification_status == VerificationStatus.VERIFIED,
            safety=_safety(visit),
            licence_status=LicenceStatus(found.licence_status),
            society_permission=SocietyPermission(found.society_permission),
            display=display,
            locality=locality,
            campuses=tuple(campuses),
            stations=tuple(stations),
            owner_business_name=owner.business_name,
            categories=tuple(
                PublicCategoryView(
                    public_id=category.public_id,
                    occupancy=Occupancy(category.occupancy),
                    label=category.label,
                    ac=category.ac,
                    attached_bath=category.attached_bath,
                    balcony=category.balcony,
                    base_rent=Paise(category.base_rent_paise),
                    security_deposit=Paise(category.security_deposit_paise),
                    charges=charges_from_json(category.mandatory_charges),
                )
                for category in categories
                if category.id in selling
            ),
            amenities=tuple(amenities),
            media=tuple(
                media[media_id]
                for media_id in media_ids
                if media_id in media and _shown(media[media_id])
            ),
        )

    async def contact(self, actor: Actor, slug: str) -> ContactDetails:
        """The owner's phone, the address and the exact point, if this person may see them.
        Every time they're shown is audited: it's part of the record that we introduced them."""
        await enforce(self._limiter, CONTACTS_PER_USER, str(actor.user_id))
        hidden = await self._flags.is_enabled(Flag.HIDE_OWNER_CONTACT)
        verified_only = await self._flags.is_enabled(Flag.VERIFIED_ONLY)
        async with self._db.begin():
            found = await self._live(slug, verified_only=verified_only)
            entitled = await self._access.entitled(
                self._db, user_id=actor.user_id, property_id=found.id
            )
            if not contact_shown(hide_owner_contact=hidden, entitled=entitled):
                raise ContactHiddenError
            exact, _ = await self._catalog.points(found.id)
            owner = (await self._catalog.owners_by_id([found.owner_id]))[found.owner_id]
            account = (await self._accounts.many([owner.user_id])).get(owner.user_id)
            await audit.record(
                self._db,
                clock=self._clock,
                actor=audit.Actor("user", actor.user_id),
                action="catalog.contact_shown",
                entity_type="property",
                entity_id=str(found.public_id),
                details={"because": "entitled" if entitled else "not_hidden"},
            )
        return ContactDetails(
            phone=None if account is None else account.phone_e164,
            address_line=found.address_line,
            exact=exact,
            location_precision=LocationPrecision(found.location_precision),
        )
