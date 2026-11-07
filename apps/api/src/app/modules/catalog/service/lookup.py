"""Catalog reads for other modules, inside the caller's transaction (it starts none), so they
never touch the catalog's tables themselves (ARCHITECTURE §5): search keeps its entries and price
summaries from what it reads here (steps 3.1 and 3.2), and visits the PGs they're to (step 3.7)."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from app.core.money import Paise
from app.modules.catalog.domain.listing import (
    GenderPolicy,
    LicenceStatus,
    Meals,
    PropertyStatus,
    VerificationStatus,
    is_public,
)
from app.modules.catalog.domain.rooms import BedStatus, CategoryStatus, Occupancy
from app.modules.catalog.repository import CatalogRepository, charges_from_json
from app.modules.geo.service import GeoLookup

if TYPE_CHECKING:
    import uuid
    from collections.abc import Collection, Sequence
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.geometry import Point
    from app.modules.catalog.domain.charges import MandatoryCharge
    from app.modules.catalog.models import Bed, Property
    from app.modules.geo.service import LocalityRef

# A card shows the first of a listing's photos that is ready: a few to choose from is plenty.
COVER_CANDIDATES: Final = 3


@dataclass(frozen=True, slots=True)
class CategoryRent:
    """An active room category with a bed to sell: its base rent, active beds and features."""

    category_id: int
    base_rent: Paise
    active_beds: int
    occupancy: Occupancy
    ac: bool
    attached_bath: bool


@dataclass(frozen=True, slots=True)
class LayoutBed:
    id: int
    public_id: uuid.UUID
    label: str
    active: bool


@dataclass(frozen=True, slots=True)
class LayoutRoom:
    id: int
    public_id: uuid.UUID
    label: str
    beds: tuple[LayoutBed, ...]


@dataclass(frozen=True, slots=True)
class LayoutCategory:
    id: int
    public_id: uuid.UUID
    label: str
    active: bool
    rooms: tuple[LayoutRoom, ...]

    @property
    def active_beds(self) -> tuple[LayoutBed, ...]:
        return tuple(bed for room in self.rooms for bed in room.beds if bed.active)


@dataclass(frozen=True, slots=True)
class BedLayout:
    """A PG's room types, rooms and beds: what inventory holds over time (ADR 0044)."""

    property_id: int
    property_public_id: uuid.UUID
    name: str
    categories: tuple[LayoutCategory, ...]


@dataclass(frozen=True, slots=True)
class BedRef:
    """A bed with where it is, for a change to what holds it."""

    id: int
    public_id: uuid.UUID
    label: str
    active: bool
    room_label: str
    category_id: int
    category_label: str
    property_id: int
    # How many share its room: single, double, triple or quad.
    occupancy: str


@dataclass(frozen=True, slots=True)
class ListedRoom:
    """An active room category of a published PG, as pricing's market check compares it."""

    property_id: int
    property_public_id: uuid.UUID
    property_name: str
    locality_id: int
    category_id: int
    category_public_id: uuid.UUID
    label: str
    occupancy: Occupancy
    base_rent: Paise


@dataclass(frozen=True, slots=True)
class PricedCategory:
    """A room category as pricing needs it: its listed rent and the owner's bounds."""

    id: int
    public_id: uuid.UUID
    label: str
    occupancy: Occupancy
    base_rent: Paise
    owner_min: Paise | None
    owner_max: Paise | None
    active: bool
    # What a quote shows beside the rent (rule 7): the deposit and every mandatory charge.
    security_deposit: Paise
    charges: tuple[MandatoryCharge, ...]


@dataclass(frozen=True, slots=True)
class PricedProperty:
    """A PG as pricing needs it: where it is, for its rent bands, and its room categories."""

    id: int
    public_id: uuid.UUID
    name: str
    slug: str
    locality_id: int
    # Whether the public may see it now, as its page decides (verified-only or not).
    public: bool
    categories: tuple[PricedCategory, ...]


@dataclass(frozen=True, slots=True)
class SearchEntry:
    """What search keeps about a listing the public can find: public details only (ADR 0026)."""

    public_id: uuid.UUID
    slug: str
    name: str
    locality: LocalityRef
    display: Point
    gender_policy: GenderPolicy
    meals: Meals
    verified: bool
    licensed: bool
    amenities: tuple[str, ...]
    # The first few photos and videos, in page order; the card's cover is the first one ready.
    media_ids: tuple[int, ...]
    published_at: datetime


@dataclass(frozen=True, slots=True)
class VisitPlace:
    """A PG as visits need it. The address and exact point are for staff, and for a student
    once a visit is booked: the visits module decides who sees them (ADR 0026, 0033)."""

    id: int
    public_id: uuid.UUID
    slug: str
    name: str
    locality: str
    address_line: str
    exact: Point
    # Whether the public may see it now, as its page decides.
    public: bool


@dataclass(frozen=True, slots=True)
class BookingPlace:
    """A PG as bookings need it: whose it is, whether it confirms bookings itself, and whether
    the public may see it now. Its address stays here until a booking is confirmed (rule 11)."""

    id: int
    public_id: uuid.UUID
    slug: str
    name: str
    locality: str
    locality_slug: str
    gender_policy: str
    owner_id: int
    instant_confirm: bool
    public: bool


@dataclass(frozen=True, slots=True)
class OwnedProperty:
    """A PG as its owner runs it (Phase 7): theirs, whatever its status."""

    id: int
    public_id: uuid.UUID
    slug: str
    name: str
    locality: str
    status: str
    verification_status: str
    licence_status: str


@dataclass(frozen=True, slots=True)
class InvoiceParty:
    """Who an invoice is to, and for which PG, as the invoice prints it (step 6.5). The owner sees
    their own PG's address on it."""

    legal_name: str
    business_name: str
    gstin: str | None
    pg_name: str
    pg_address: str


@dataclass(frozen=True, slots=True)
class SellableRoom:
    """A room with its beds that can be sold, by internal id, for a hold to choose from."""

    id: int
    label: str
    bed_ids: tuple[int, ...]


class CatalogLookup:
    def __init__(self, db: AsyncSession) -> None:
        self._catalog = CatalogRepository(db)
        self._geo = GeoLookup(db)

    async def rents(self, property_id: int) -> list[CategoryRent]:
        return [
            CategoryRent(
                category_id=row.category_id,
                base_rent=Paise(row.base_rent_paise),
                active_beds=row.active_beds,
                occupancy=Occupancy(row.occupancy),
                ac=row.ac,
                attached_bath=row.attached_bath,
            )
            for row in await self._catalog.category_rents(property_id)
        ]

    async def priced_property(
        self, public_id: uuid.UUID, *, verified_only: bool = False
    ) -> PricedProperty | None:
        """A PG with every room category it has, for its pricing rules and quotes (ADR 0038)."""
        found = await self._catalog.property(public_id)
        return None if found is None else await self._priced(found, verified_only=verified_only)

    async def priced_property_by_id(
        self, property_id: int, *, verified_only: bool = False
    ) -> PricedProperty | None:
        found = (await self._catalog.properties_by_id([property_id])).get(property_id)
        return None if found is None else await self._priced(found, verified_only=verified_only)

    async def priced_property_by_slug(
        self, slug: str, *, verified_only: bool
    ) -> PricedProperty | None:
        found = await self._catalog.property_by_slug(slug)
        return None if found is None else await self._priced(found, verified_only=verified_only)

    async def bed_layout(self, property_id: int) -> BedLayout | None:
        """A PG's room types with their rooms and beds, by its internal id."""
        found = (await self._catalog.properties_by_id([property_id])).get(property_id)
        return None if found is None else await self._layout(found)

    async def bed_layout_of(self, public_id: uuid.UUID) -> BedLayout | None:
        found = await self._catalog.property(public_id)
        return None if found is None else await self._layout(found)

    async def _layout(self, found: Property) -> BedLayout:
        categories = await self._catalog.categories(found.id)
        rooms = await self._catalog.rooms_of([category.id for category in categories])
        beds = await self._catalog.beds_of([room.id for room in rooms])
        return BedLayout(
            property_id=found.id,
            property_public_id=found.public_id,
            name=found.name,
            categories=tuple(
                LayoutCategory(
                    id=category.id,
                    public_id=category.public_id,
                    label=category.label,
                    active=category.status == CategoryStatus.ACTIVE,
                    rooms=tuple(
                        LayoutRoom(
                            id=room.id,
                            public_id=room.public_id,
                            label=room.label,
                            beds=tuple(
                                LayoutBed(
                                    id=bed.id,
                                    public_id=bed.public_id,
                                    label=bed.label,
                                    active=bed.status == BedStatus.ACTIVE,
                                )
                                for bed in beds
                                if bed.room_id == room.id
                            ),
                        )
                        for room in rooms
                        if room.room_category_id == category.id
                    ),
                )
                for category in categories
            ),
        )

    async def active_bed_ids(self, category_id: int) -> list[int]:
        """A room type's beds that can be sold, by internal id."""
        return await self._catalog.active_bed_ids(category_id)

    async def bed_ref(self, bed_id: int) -> BedRef:
        """A bed by its internal id, with where it is."""
        found = await self._catalog.bed_by_id(bed_id)
        return await self._ref(found)

    async def locked_bed(self, public_id: uuid.UUID) -> BedRef | None:
        """A bed, held until the transaction ends so changes to what holds it go one at a time
        (ARCHITECTURE §7.3)."""
        bed = await self._catalog.bed(public_id, lock=True)
        return None if bed is None else await self._ref(bed)

    async def _ref(self, bed: Bed) -> BedRef:
        place = await self._catalog.bed_place(bed.id)
        return BedRef(
            id=bed.id,
            public_id=bed.public_id,
            label=bed.label,
            active=bed.status == BedStatus.ACTIVE,
            room_label=place.room_label,
            category_id=place.category_id,
            category_label=place.category_label,
            property_id=place.property_id,
            occupancy=place.occupancy,
        )

    async def listed_rooms(self) -> list[ListedRoom]:
        """Every active room of every published PG: the market pricing's alerts compare
        listed rents with (ADR 0043)."""
        return [
            ListedRoom(
                property_id=row.property_id,
                property_public_id=row.property_public_id,
                property_name=row.property_name,
                locality_id=row.locality_id,
                category_id=row.category_id,
                category_public_id=row.category_public_id,
                label=row.label,
                occupancy=Occupancy(row.occupancy),
                base_rent=Paise(row.base_rent_paise),
            )
            for row in await self._catalog.listed_rooms()
        ]

    async def locality_rents(
        self, locality_id: int, occupancy: Occupancy, *, except_property: int
    ) -> list[Paise]:
        """The listed rents of the active room categories of this occupancy in the locality's
        published PGs, but one: the market a PG's prices sit in (ARCHITECTURE §8.6)."""
        rents = await self._catalog.locality_rents(
            locality_id, occupancy, except_property=except_property
        )
        return [Paise(rent) for rent in rents]

    async def beds(self, property_id: int) -> dict[int, int]:
        """Each room category's active beds, by its internal id."""
        return {
            row.category_id: row.active_beds
            for row in await self._catalog.category_rents(property_id)
        }

    async def priced_category(
        self, public_id: uuid.UUID, *, verified_only: bool
    ) -> tuple[PricedProperty, PricedCategory] | None:
        """A room category with its PG, for a quote."""
        category = await self._catalog.category(public_id)
        if category is None:
            return None
        place = await self.priced_property_by_id(category.property_id, verified_only=verified_only)
        assert place is not None  # noqa: S101 - a category's PG exists (foreign key)
        found = next(item for item in place.categories if item.id == category.id)
        return place, found

    async def _priced(self, found: Property, *, verified_only: bool) -> PricedProperty:
        return PricedProperty(
            id=found.id,
            public_id=found.public_id,
            name=found.name,
            slug=found.slug,
            locality_id=found.locality_id,
            public=is_public(
                PropertyStatus(found.status),
                VerificationStatus(found.verification_status),
                verified_only=verified_only,
            ),
            categories=tuple(
                PricedCategory(
                    id=row.id,
                    public_id=row.public_id,
                    label=row.label,
                    occupancy=Occupancy(row.occupancy),
                    base_rent=Paise(row.base_rent_paise),
                    owner_min=None
                    if row.owner_min_rent_paise is None
                    else Paise(row.owner_min_rent_paise),
                    owner_max=None
                    if row.owner_max_rent_paise is None
                    else Paise(row.owner_max_rent_paise),
                    active=row.status == CategoryStatus.ACTIVE,
                    security_deposit=Paise(row.security_deposit_paise),
                    charges=charges_from_json(row.mandatory_charges),
                )
                for row in await self._catalog.categories(found.id)
            ),
        )

    async def search_entry(self, property_id: int) -> SearchEntry | None:
        """The listing as search shows it, or None when the public can't find it: not
        published, or its verification failed or was suspended. Whether only verified listings
        show is the flag's to say at search time."""
        found = (await self._catalog.properties_by_id([property_id])).get(property_id)
        if found is None or not is_public(
            PropertyStatus(found.status),
            VerificationStatus(found.verification_status),
            verified_only=False,
        ):
            return None
        assert found.published_at is not None  # noqa: S101 - set when first published
        display = await self._catalog.display_point(found.id)
        locality = (await self._geo.localities([found.locality_id]))[found.locality_id]
        media = (await self._catalog.media_of([found.id])).get(found.id, [])
        return SearchEntry(
            public_id=found.public_id,
            slug=found.slug,
            name=found.name,
            locality=locality,
            display=display,
            gender_policy=GenderPolicy(found.gender_policy),
            meals=Meals(found.meals),
            verified=found.verification_status == VerificationStatus.VERIFIED,
            licensed=found.licence_status == LicenceStatus.LICENSED,
            amenities=tuple(await self._catalog.amenities_of(found.id)),
            media_ids=tuple(media[:COVER_CANDIDATES]),
            published_at=found.published_at,
        )

    async def visit_place(self, slug: str, *, verified_only: bool) -> VisitPlace | None:
        """The PG with this slug, whether or not the public may see it now."""
        found = await self._catalog.property_by_slug(slug)
        if found is None:
            return None
        return (await self.visit_places([found.id], verified_only=verified_only))[found.id]

    async def visit_places(
        self, ids: Collection[int], *, verified_only: bool
    ) -> dict[int, VisitPlace]:
        """PGs by internal id: three queries, however many."""
        found = await self._catalog.properties_by_id(ids)
        exact = await self._catalog.exact_points(found.keys())
        localities = await self._geo.localities({row.locality_id for row in found.values()})
        return {
            row.id: VisitPlace(
                id=row.id,
                public_id=row.public_id,
                slug=row.slug,
                name=row.name,
                locality=localities[row.locality_id].name,
                address_line=row.address_line,
                exact=exact[row.id],
                public=is_public(
                    PropertyStatus(row.status),
                    VerificationStatus(row.verification_status),
                    verified_only=verified_only,
                ),
            )
            for row in found.values()
        }

    async def booking_places(
        self, ids: Collection[int], *, verified_only: bool
    ) -> dict[int, BookingPlace]:
        """PGs by internal id, as bookings need them: two queries, however many."""
        found = await self._catalog.properties_by_id(ids)
        localities = await self._geo.localities({row.locality_id for row in found.values()})
        return {
            row.id: BookingPlace(
                id=row.id,
                public_id=row.public_id,
                slug=row.slug,
                name=row.name,
                locality=localities[row.locality_id].name,
                locality_slug=localities[row.locality_id].slug,
                gender_policy=row.gender_policy,
                owner_id=row.owner_id,
                instant_confirm=row.instant_confirm,
                public=is_public(
                    PropertyStatus(row.status),
                    VerificationStatus(row.verification_status),
                    verified_only=verified_only,
                ),
            )
            for row in found.values()
        }

    async def category_labels(self, ids: Collection[int]) -> dict[int, str]:
        """Room types' labels by internal id: one query, however many."""
        return await self._catalog.category_labels(ids)

    async def property_ids_named(self, text: str, *, limit: int) -> list[int]:
        """The PGs whose names contain ``text``, for ops looking one up."""
        return await self._catalog.property_ids_named(text, limit=limit)

    async def owner_id_of_user(self, user_id: int) -> int | None:
        """The owner record of a person signed in by phone, if they're an owner."""
        owner = await self._catalog.owner_of_user(user_id)
        return None if owner is None else owner.id

    async def owned_properties(self, user_id: int) -> list[OwnedProperty]:
        """The PGs of the owner signed in as ``user_id``, by name; none for anyone else."""
        owner = await self._catalog.owner_of_user(user_id)
        if owner is None:
            return []
        found = await self._catalog.properties_of_owner(owner.id)
        localities = await self._geo.localities({row.locality_id for row in found})
        return [
            OwnedProperty(
                id=row.id,
                public_id=row.public_id,
                slug=row.slug,
                name=row.name,
                locality=localities[row.locality_id].name,
                status=row.status,
                verification_status=row.verification_status,
                licence_status=row.licence_status,
            )
            for row in found
        ]

    async def owned_property(self, user_id: int, public_id: uuid.UUID) -> OwnedProperty | None:
        """The PG, if the owner signed in as ``user_id`` owns it: anyone else's is None, and their
        route answers 404."""
        for owned in await self.owned_properties(user_id):
            if owned.public_id == public_id:
                return owned
        return None

    async def owns(self, user_id: int, property_id: int) -> bool:
        """Whether the person signed in as ``user_id`` owns the PG with this internal id."""
        owner = await self._catalog.owner_of_user(user_id)
        if owner is None:
            return False
        found = (await self._catalog.properties_by_id({property_id})).get(property_id)
        return found is not None and found.owner_id == owner.id

    async def owner_names(self, owner_ids: Collection[int]) -> dict[int, str]:
        """Owners' business names by owner id: one query, however many."""
        found = await self._catalog.owners_by_id(owner_ids)
        return {owner_id: owner.business_name for owner_id, owner in found.items()}

    async def invoice_party(self, owner_id: int, property_id: int) -> InvoiceParty:
        owner = (await self._catalog.owners_by_id({owner_id}))[owner_id]
        place = (await self._catalog.properties_by_id({property_id}))[property_id]
        locality = (await self._geo.localities({place.locality_id}))[place.locality_id]
        return InvoiceParty(
            legal_name=owner.legal_name,
            business_name=owner.business_name,
            gstin=owner.gstin,
            pg_name=place.name,
            pg_address=f"{place.address_line}, {locality.name}",
        )

    async def owner_user_ids(self, owner_ids: Collection[int]) -> dict[int, int]:
        """Each owner's account, by owner id: who an owner's texts go to."""
        return await self._catalog.owner_user_ids(owner_ids)

    async def sellable_rooms(self, category_id: int) -> tuple[SellableRoom, ...]:
        """A room type's rooms with their active beds. Nothing is locked: a hold locks only the
        bed it takes (``lock_first_bed``, ARCHITECTURE §7.3)."""
        rooms: dict[int, tuple[str, list[int]]] = {}
        for bed, room, label in await self._catalog.active_beds(category_id):
            rooms.setdefault(room, (label, []))[1].append(bed)
        return tuple(
            SellableRoom(id=room, label=label, bed_ids=tuple(beds))
            for room, (label, beds) in rooms.items()
        )

    async def lock_first_bed(self, bed_ids: Sequence[int]) -> int | None:
        """The first of these beds, in the order given, that no other hold is taking, locked
        until the transaction ends; None when every one is being taken (§7.3)."""
        return await self._catalog.lock_first_bed(bed_ids)

    async def property_ids_in(self, locality_id: int) -> list[int]:
        """Every listing of a locality, by internal id."""
        return await self._catalog.property_ids_in(locality_id)

    async def property_ids(self, *, after: int | None, limit: int) -> list[int]:
        """Every property's internal id, a page at a time (``after`` the last one seen)."""
        return await self._catalog.property_ids_after(after, limit=limit)
