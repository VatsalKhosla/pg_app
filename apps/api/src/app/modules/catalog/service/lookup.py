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
from app.modules.catalog.domain.rooms import Occupancy
from app.modules.catalog.repository import CatalogRepository
from app.modules.geo.service import GeoLookup

if TYPE_CHECKING:
    import uuid
    from collections.abc import Collection
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.geometry import Point
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

    async def property_ids(self, *, after: int | None, limit: int) -> list[int]:
        """Every property's internal id, a page at a time (``after`` the last one seen)."""
        return await self._catalog.property_ids_after(after, limit=limit)
