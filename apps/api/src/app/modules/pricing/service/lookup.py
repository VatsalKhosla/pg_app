"""Prices for other modules (step 4.7, ADR 0042), inside the caller's transaction (it starts none):
search keeps each room's rent range for every month a student can move in, from the same inputs
and engine as a quote, so the map and search agree with the PG page."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.core.calendar import india_date
from app.modules.catalog.service import CatalogLookup
from app.modules.pricing.domain.engine import ImpossibleBoundsError, quote
from app.modules.pricing.domain.quotes import DEFAULT_STAY_MONTHS, move_in_days
from app.modules.pricing.service.inputs import PricingInputs

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence
    from datetime import date

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.clock import Clock
    from app.core.money import Paise
    from app.modules.pricing.occupancy import BedsTaken

logger = structlog.stdlib.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RentRange:
    """The least and the most a month's move-ins are quoted, for one room."""

    low: Paise
    high: Paise


class PricingLookup:
    def __init__(self, db: AsyncSession, clock: Clock, *, beds: BedsTaken) -> None:
        self._clock = clock
        self._catalog = CatalogLookup(db)
        self._inputs = PricingInputs(db, beds=beds)

    async def month_rents(
        self,
        property_id: int,
        months: Sequence[date],
        *,
        only: Collection[int] | None = None,
        stay_months: int = DEFAULT_STAY_MONTHS,
    ) -> dict[tuple[int, date], RentRange]:
        """Each active room's rent range for each month (its first day), by the room's internal
        id: the least and the most a quote made today says for a move-in on any day of it still
        to come, for a ``stay_months`` stay; only the rooms in ``only`` when given. Months past
        the booking horizon are priced as the editor's preview prices them. A room whose limits
        leave no rent has none (ops are told).
        """
        now = self._clock.now()
        today = india_date(now)
        place = await self._catalog.priced_property_by_id(property_id)
        if place is None:
            return {}
        pricing = await self._inputs.active(place, now=now)
        ranges: dict[tuple[int, date], RentRange] = {}
        for category in place.categories:
            if not category.active or (only is not None and category.id not in only):
                continue
            found: dict[tuple[int, date], RentRange] = {}
            try:
                for month in months:
                    rents = [
                        quote(
                            await self._inputs.context(pricing, category, day, stay_months, today)
                        ).monthly_rent_paise
                        for day in move_in_days(month, today)
                    ]
                    if rents:
                        found[category.id, month] = RentRange(min(rents), max(rents))
            except ImpossibleBoundsError:
                logger.error("no rent the bounds allow", property=str(place.public_id))
                continue
            ranges.update(found)
        return ranges
