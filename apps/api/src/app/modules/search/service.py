"""Keeping price summaries fresh (step 3.1, ADR 0027). Both use cases run inside a job's
transaction (they start none): the worker commits the summaries with the job's "done" mark.

- After each catalog change to a listing's rents, rooms or beds, its summaries are worked out
  again (``catalog.inventory_changed``), so they follow a rent change within seconds.
- Every night, every listing's are, so the months roll forward: the nightly job adds one job per
  listing, at most once a day each.
"""

from typing import TYPE_CHECKING, Final

import structlog

from app.core.calendar import india_date
from app.core.outbox import enqueue
from app.modules.catalog.service import CatalogLookup
from app.modules.search.domain.summaries import CategoryRent, months_from, summarise
from app.modules.search.repository import SummaryRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.clock import Clock

RECOMPUTE: Final = "search.recompute_price_summaries"
RECOMPUTE_ALL: Final = "search.recompute_all_price_summaries"
# Listings read per query by the nightly fan-out.
_PAGE: Final = 500

logger = structlog.stdlib.get_logger(__name__)


class PriceSummaries:
    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._db = db
        self._clock = clock
        self._catalog = CatalogLookup(db)
        self._summaries = SummaryRepository(db)

    async def recompute(self, property_id: int) -> int:
        """Work out one listing's summaries again, from its rents and beds now; how many."""
        now = self._clock.now()
        rents = await self._catalog.rents(property_id)
        summaries = summarise(
            [CategoryRent(rent.category_id, rent.base_rent, rent.active_beds) for rent in rents],
            months_from(india_date(now)),
        )
        await self._summaries.replace(property_id, summaries, computed_at=now)
        return len(summaries)

    async def recompute_all(self) -> int:
        """Ask for every listing's summaries again, one job each; a second run the same day
        adds nothing. How many jobs it added."""
        today = india_date(self._clock.now()).isoformat()
        added, after = 0, None
        while ids := await self._catalog.property_ids(after=after, limit=_PAGE):
            for property_id in ids:
                added += await enqueue(
                    self._db,
                    RECOMPUTE,
                    {"property_id": property_id},
                    clock=self._clock,
                    dedupe_key=f"{RECOMPUTE}:{property_id}:{today}",
                )
            after = ids[-1]
        logger.info("price summaries queued for every listing", jobs=added)
        return added
