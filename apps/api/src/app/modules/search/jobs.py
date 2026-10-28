"""The search module's job handlers (app/jobs.py registers them, and the nightly schedule)."""

from typing import TYPE_CHECKING

from app.modules.search.service import REFRESH, REFRESH_ALL, SearchIndex

if TYPE_CHECKING:
    from app.core.outbox import JobContext, JobPayload

__all__ = ["REFRESH", "REFRESH_ALL", "changed_handler", "refresh_all_handler", "refresh_handler"]


async def changed_handler(context: JobContext, payload: JobPayload) -> None:
    """After a catalog change: the listing's search entry and price summaries, its change time,
    and the web app told which of its pages are out of date (ADR 0032)."""
    await SearchIndex(context.session, context.clock).refresh(
        int(payload["property_id"]), changed=True
    )


async def refresh_handler(context: JobContext, payload: JobPayload) -> None:
    """One listing's search entry and price summaries, worked out again nightly."""
    await SearchIndex(context.session, context.clock).refresh(int(payload["property_id"]))


async def refresh_all_handler(context: JobContext, _payload: JobPayload) -> None:
    await SearchIndex(context.session, context.clock).refresh_all()
