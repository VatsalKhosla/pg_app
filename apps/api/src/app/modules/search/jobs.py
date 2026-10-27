"""The search module's job handlers (app/jobs.py registers them, and the nightly schedule)."""

from typing import TYPE_CHECKING

from app.modules.search.service import REFRESH, REFRESH_ALL, SearchIndex

if TYPE_CHECKING:
    from app.core.outbox import JobContext, JobPayload

__all__ = ["REFRESH", "REFRESH_ALL", "refresh_all_handler", "refresh_handler"]


async def refresh_handler(context: JobContext, payload: JobPayload) -> None:
    """One listing's search entry and price summaries: after a catalog change, or nightly."""
    await SearchIndex(context.session, context.clock).refresh(int(payload["property_id"]))


async def refresh_all_handler(context: JobContext, _payload: JobPayload) -> None:
    await SearchIndex(context.session, context.clock).refresh_all()
