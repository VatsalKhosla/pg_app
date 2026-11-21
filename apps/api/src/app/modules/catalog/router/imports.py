"""Owners and their PGs from a filled-in template (ADR 0072): ops check a file, then import it."""

from fastapi import APIRouter, Request

from app.core.clock import ClockDep
from app.core.current_actor import CurrentActor
from app.core.db import DbSession
from app.modules.catalog.router.listings import require_listing_staff
from app.modules.catalog.schemas import ImportedPgResult, ListingImportReport, ListingImportRequest
from app.modules.catalog.service.imports import ImportReport, ListingImport

router = APIRouter(prefix="/v1", tags=["catalog"])


def _report(report: ImportReport) -> ListingImportReport:
    return ListingImportReport(
        done=report.done,
        pgs=[
            ImportedPgResult(
                row=outcome.row,
                name=outcome.name,
                owner_name=outcome.owner_name,
                owner=outcome.owner,
                listing=outcome.listing,
                listing_id=outcome.listing_id,
                room_types=outcome.room_types,
                problems=list(outcome.problems),
            )
            for outcome in report.pgs
        ],
        problems=list(report.problems),
    )


@router.post("/ops/listing-imports", summary="Check, then import, owners and their PGs")
async def import_listings(
    body: ListingImportRequest,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> ListingImportReport:
    """The template's rows, one per room type (``GET /listing-import-template.csv`` on the web
    app). With ``dryRun`` (the default), says what it would make and what's wrong, making
    nothing. Without it, adds each owner (or finds them by phone) and makes each PG a draft with
    its room types and amenities; a PG without a pin waits for one, and running the file again
    makes nothing twice."""
    require_listing_staff(actor)
    service = ListingImport(
        db, clock, buckets=request.app.state.media_buckets, flags=request.app.state.flags
    )
    report = await service.check(body.csv) if body.dry_run else await service.run(actor, body.csv)
    return _report(report)
