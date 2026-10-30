"""The search module's job handlers (app/jobs.py registers them, and the nightly schedule). Those
that price listings get the port that says how full a room is (ADR 0039)."""

from typing import TYPE_CHECKING

from app.modules.search.service import REFRESH, REFRESH_ALL, REPRICE, SearchIndex

if TYPE_CHECKING:
    from app.core.outbox import JobContext, JobHandler, JobPayload
    from app.modules.pricing.occupancy import BedsTaken

__all__ = [
    "REFRESH",
    "REFRESH_ALL",
    "REPRICE",
    "band_changed_handler",
    "caps_changed_handler",
    "changed_handler",
    "refresh_all_handler",
    "refresh_handler",
]


def changed_handler(beds: BedsTaken) -> JobHandler:
    """After a change to a listing or its prices: its search entry and price summaries, its
    change time, and the web app told which of its pages are out of date (ADR 0032)."""

    async def handle(context: JobContext, payload: JobPayload) -> None:
        await SearchIndex(context.session, context.clock, beds=beds).refresh(
            int(payload["property_id"]), changed=True
        )

    return handle


def refresh_handler(beds: BedsTaken) -> JobHandler:
    """One listing's search entry and price summaries, worked out again nightly."""

    async def handle(context: JobContext, payload: JobPayload) -> None:
        await SearchIndex(context.session, context.clock, beds=beds).refresh(
            int(payload["property_id"])
        )

    return handle


def refresh_all_handler(beds: BedsTaken) -> JobHandler:
    async def handle(context: JobContext, _payload: JobPayload) -> None:
        await SearchIndex(context.session, context.clock, beds=beds).refresh_all()

    return handle


def band_changed_handler(beds: BedsTaken) -> JobHandler:
    """A band began or ended: the locality's listings are priced again (ADR 0042)."""

    async def handle(context: JobContext, payload: JobPayload) -> None:
        await SearchIndex(context.session, context.clock, beds=beds).reprice_locality(
            int(payload["locality_id"]), reason=f"band:{payload['band']}:{payload['change']}"
        )

    return handle


def caps_changed_handler(beds: BedsTaken) -> JobHandler:
    """The caps changed: every listing is priced again, once for this version (ADR 0042)."""

    async def handle(context: JobContext, payload: JobPayload) -> None:
        await SearchIndex(context.session, context.clock, beds=beds).refresh_all(
            reason=f"caps:{payload['version']}"
        )

    return handle
