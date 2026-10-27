"""Catalog reads for other modules, inside the caller's transaction (it starts none), so they
never touch the catalog's tables themselves (ARCHITECTURE §5): search's price summaries read
listings' rents and beds here (step 3.1)."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.money import Paise
from app.modules.catalog.repository import CatalogRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class CategoryRent:
    """An active room category with a bed to sell: its base rent and its active beds."""

    category_id: int
    base_rent: Paise
    active_beds: int


class CatalogLookup:
    def __init__(self, db: AsyncSession) -> None:
        self._catalog = CatalogRepository(db)

    async def rents(self, property_id: int) -> list[CategoryRent]:
        return [
            CategoryRent(category_id=category_id, base_rent=Paise(rent), active_beds=beds)
            for category_id, rent, beds in await self._catalog.category_rents(property_id)
        ]

    async def property_ids(self, *, after: int | None, limit: int) -> list[int]:
        """Every property's internal id, a page at a time (``after`` the last one seen)."""
        return await self._catalog.property_ids_after(after, limit=limit)
