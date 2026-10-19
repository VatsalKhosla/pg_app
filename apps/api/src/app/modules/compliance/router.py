"""Data request routes (ARCHITECTURE §12 and §15): people's own, and the ops queue."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, status

from app.core.clock import ClockDep
from app.core.current_actor import CurrentActor
from app.core.db import DbSession
from app.core.errors import ForbiddenError
from app.core.pagination import PageParams
from app.modules.compliance.domain.requests import DataRequestKind, DataRequestStatus
from app.modules.compliance.models import DataRequest
from app.modules.compliance.policies import can_review_data_requests
from app.modules.compliance.schemas import (
    DataRequestCreate,
    DataRequestInfo,
    DataRequestPage,
    DataRequestQueue,
    DataRequestResolution,
    QueuedDataRequest,
    Requester,
)
from app.modules.compliance.service import DataRequestService, QueuedRequest

router = APIRouter(prefix="/v1", tags=["compliance"])


def _service(request: Request, db: DbSession, clock: ClockDep) -> DataRequestService:
    return DataRequestService(db, clock, limiter=request.app.state.rate_limiter)


def _info(request: DataRequest) -> DataRequestInfo:
    return DataRequestInfo(
        id=request.public_id,
        kind=DataRequestKind(request.kind),
        status=DataRequestStatus(request.status),
        requested_at=request.requested_at,
        resolved_at=request.resolved_at,
        expires_at=request.expires_at,
        note=request.note,
    )


def _queued(item: QueuedRequest) -> QueuedDataRequest:
    person = item.person
    return QueuedDataRequest(
        **_info(item.request).model_dump(),
        requester=None
        if person is None
        else Requester(id=person.public_id, phone=person.phone_e164, name=person.name),
    )


@router.post(
    "/me/data-requests",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ask for a copy of my data, or for my account's deletion",
)
async def ask(
    body: DataRequestCreate, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> DataRequestInfo:
    """An export is ready within minutes, then downloadable for 7 days; a deletion goes to the
    team. Asking again while one is open answers that one."""
    return _info(await _service(request, db, clock).ask(actor, body.kind))


@router.get("/me/data-requests", summary="My data requests")
async def my_requests(
    request: Request, actor: CurrentActor, page: PageParams, db: DbSession, clock: ClockDep
) -> DataRequestPage:
    requests, next_cursor = await _service(request, db, clock).mine(actor, page)
    return DataRequestPage(items=[_info(item) for item in requests], next_cursor=next_cursor)


@router.get(
    "/me/data-requests/{request_id}/file",
    response_class=Response,
    summary="Download my data",
    responses={200: {"content": {"application/json": {}}, "description": "The export"}},
)
async def download(
    request_id: uuid.UUID, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> Response:
    """The export's file, while it is ready; only for the person who asked (404 for anyone
    else, staff included). Never cached."""
    data_request, content = await _service(request, db, clock).export_file(actor, request_id)
    day = data_request.requested_at.date().isoformat()
    return Response(
        content,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="my-data-{day}.json"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/ops/data-requests", summary="The data request queue")
async def queue(
    request: Request,
    *,
    actor: CurrentActor,
    page: PageParams,
    db: DbSession,
    clock: ClockDep,
    request_status: Annotated[DataRequestStatus | None, Query(alias="status")] = None,
) -> DataRequestQueue:
    """Ops and admins, in a staff session: every request, oldest first, optionally only those in
    one status (``status=received`` for the ones waiting)."""
    if not can_review_data_requests(actor):
        raise ForbiddenError
    items, next_cursor = await _service(request, db, clock).queue(page, status=request_status)
    return DataRequestQueue(items=[_queued(item) for item in items], next_cursor=next_cursor)


@router.post(
    "/ops/data-requests/{request_id}/resolve", summary="Complete or reject a deletion request"
)
async def resolve(
    request_id: uuid.UUID,
    body: DataRequestResolution,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> QueuedDataRequest:
    """Ops and admins: record what was done about a deletion request, or why it was refused (the
    person sees the note). Audited. 409 INVALID_TRANSITION for an export or a resolved one."""
    if not can_review_data_requests(actor):
        raise ForbiddenError
    item = await _service(request, db, clock).resolve(
        actor, request_id, outcome=DataRequestStatus(body.outcome), note=body.note
    )
    return _queued(item)
