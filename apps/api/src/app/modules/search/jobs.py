"""The search module's job handlers (app/jobs.py registers them, and the nightly schedule)."""

from typing import TYPE_CHECKING

from app.modules.search.service import RECOMPUTE, RECOMPUTE_ALL, PriceSummaries

if TYPE_CHECKING:
    from app.core.outbox import JobContext, JobPayload

__all__ = ["RECOMPUTE", "RECOMPUTE_ALL", "recompute_all_handler", "recompute_handler"]


async def recompute_handler(context: JobContext, payload: JobPayload) -> None:
    """One listing's summaries, after a catalog change or for the nightly refresh."""
    await PriceSummaries(context.session, context.clock).recompute(int(payload["property_id"]))


async def recompute_all_handler(context: JobContext, _payload: JobPayload) -> None:
    await PriceSummaries(context.session, context.clock).recompute_all()
