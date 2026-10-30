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
from app.modules.catalog.domain.rooms import CategoryStatus, Occupancy
from app.modules.catalog.repository import CatalogRepository, charges_from_json
from app.modules.geo.service import GeoLookup

if TYPE_CHECKING:
    import uuid
    from collections.abc import Collection
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.geometry import Point
    from app.modules.catalog.domain.charges import MandatoryCharge
    from app.modules.catalog.models import Property
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

    async def property_ids_in(self, locality_id: int) -> list[int]:
        """Every listing of a locality, by internal id."""
        return await self._catalog.property_ids_in(locality_id)

    async def property_ids(self, *, after: int | None, limit: int) -> list[int]:
        """Every property's internal id, a page at a time (``after`` the last one seen)."""
        return await self._catalog.property_ids_after(after, limit=limit)
