"""Reads and writes of the search module's own tables."""

from typing import TYPE_CHECKING

from sqlalchemy import delete, insert, select

from app.modules.search.models import PropertyPriceSummary

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.search.domain.summaries import MonthSummary


class SummaryRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def replace(
        self, property_id: int, summaries: Sequence[MonthSummary], *, computed_at: datetime
    ) -> None:
        """A property's summaries, all at once: readers see the old set or the new one."""
        await self._db.execute(
            delete(PropertyPriceSummary).where(PropertyPriceSummary.property_id == property_id)
        )
        if summaries:
            await self._db.execute(
                insert(PropertyPriceSummary),
                [
                    {
                        "property_id": property_id,
                        "room_category_id": summary.category_id,
                        "month": summary.month,
                        "min_rent_paise": summary.min_rent,
                        "max_rent_paise": summary.max_rent,
                        "available_beds": summary.available_beds,
                        "computed_at": computed_at,
                    }
                    for summary in summaries
                ],
            )

    async def of_property(self, property_id: int) -> list[PropertyPriceSummary]:
        found = await self._db.scalars(
            select(PropertyPriceSummary)
            .where(PropertyPriceSummary.property_id == property_id)
            .order_by(PropertyPriceSummary.room_category_id, PropertyPriceSummary.month)
        )
        return list(found)
