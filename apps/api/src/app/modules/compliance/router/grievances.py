"""Grievance routes (ARCHITECTURE §15; step 3.8, ADR 0034): anyone complains, people see their
own, and the grievance officer's team works the queue."""

from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from fastapi.exceptions import RequestValidationError

from app.core.clock import ClockDep
from app.core.current_actor import CurrentActor, OptionalActor
from app.core.db import DbSession
from app.core.errors import ForbiddenError
from app.core.pagination import PageParams
from app.core.ratelimit import client_ip
from app.modules.compliance.domain.grievances import (
    GrievanceCategory,
    GrievanceStatus,
    can_move,
)
from app.modules.compliance.models import Grievance
from app.modules.compliance.policies import can_handle_grievances
from app.modules.compliance.schemas import (
    Complainant,
    GrievanceAcknowledgement,
    GrievanceCreate,
    GrievanceReceipt,
    GrievanceResolution,
    MyGrievance,
    MyGrievanceList,
    StaffGrievance,
    StaffGrievancePage,
)
from app.modules.compliance.service import GrievanceService
from app.modules.compliance.service.grievances import Complaint, GrievanceView

router = APIRouter(prefix="/v1", tags=["compliance"])


def _service(request: Request, db: DbSession, clock: ClockDep) -> GrievanceService:
    return GrievanceService(
        db,
        clock,
        limiter=request.app.state.rate_limiter,
        human_check=request.app.state.human_check,
    )


def _receipt(grievance: Grievance) -> GrievanceReceipt:
    return GrievanceReceipt(
        ticket_number=grievance.ticket_number,
        status=GrievanceStatus(grievance.status),
        received_at=grievance.received_at,
        acknowledge_by=grievance.acknowledge_by,
        resolve_by=grievance.resolve_by,
    )


def _mine(grievance: Grievance) -> MyGrievance:
    return MyGrievance(
        **_receipt(grievance).model_dump(),
        category=GrievanceCategory(grievance.category),
        reference=grievance.reference,
        details=grievance.details,
        acknowledged_at=grievance.acknowledged_at,
        reply=grievance.reply,
        resolved_at=grievance.resolved_at,
        resolution=grievance.resolution,
    )


def _staff(view: GrievanceView) -> StaffGrievance:
    grievance = view.grievance
    current = GrievanceStatus(grievance.status)
    return StaffGrievance(
        **_mine(grievance).model_dump(),
        complainant=Complainant(
            name=grievance.name,
            phone=grievance.phone_e164,
            email=grievance.email,
            account=view.account,
        ),
        late=view.late,
        next_statuses=[target for target in GrievanceStatus if can_move(current, target)],
    )


def _missing(field: str, message: str) -> dict[str, object]:
    return {"type": "missing", "loc": ("body", field), "msg": message, "input": None}


@router.post(
    "/grievances",
    status_code=status.HTTP_201_CREATED,
    summary="Complain to the grievance officer",
)
async def complain(
    body: GrievanceCreate,
    request: Request,
    actor: OptionalActor,
    db: DbSession,
    clock: ClockDep,
) -> GrievanceReceipt:
    """Anyone may complain and gets a ticket number. Signed out, a name and a phone number or
    email address are needed, with a human check token (400 HUMAN_CHECK_FAILED); signed in, the
    account's phone is the contact and is texted as the complaint moves. Acknowledged within 48
    hours and resolved within a month (the E-Commerce Rules)."""
    if actor is None:
        problems = []
        if body.name is None:
            problems.append(_missing("name", "Enter your name."))
        if body.phone is None and body.email is None:
            problems.append(_missing("phone", "Enter a phone number or an email address."))
        if problems:
            raise RequestValidationError(problems)
    grievance = await _service(request, db, clock).submit(
        actor,
        Complaint(
            category=body.category,
            details=body.details,
            reference=body.reference,
            name=body.name,
            phone_e164=None if actor is not None else body.phone,
            email=body.email,
        ),
        human_check_token=body.human_check_token,
        ip_address=client_ip(request),
    )
    return _receipt(grievance)


@router.get("/me/grievances", summary="My complaints and their replies")
async def my_grievances(
    request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> MyGrievanceList:
    """The complaints made while signed in to this account, newest first."""
    return MyGrievanceList(
        items=[_mine(item) for item in await _service(request, db, clock).mine(actor)]
    )


@router.get("/ops/grievances", summary="The grievance queue")
async def grievance_queue(
    request: Request,
    *,
    actor: CurrentActor,
    page: PageParams,
    db: DbSession,
    clock: ClockDep,
    grievance_status: Annotated[GrievanceStatus | None, Query(alias="status")] = None,
) -> StaffGrievancePage:
    """Ops and admins, in a staff session: every grievance, oldest first (the order they fall
    due), optionally only those in one status. ``late`` marks a missed deadline."""
    if not can_handle_grievances(actor):
        raise ForbiddenError
    items, next_cursor = await _service(request, db, clock).page(page, status=grievance_status)
    return StaffGrievancePage(items=[_staff(item) for item in items], next_cursor=next_cursor)


@router.get("/ops/grievances/{ticket_number}", summary="A grievance")
async def grievance(
    ticket_number: str, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> StaffGrievance:
    """Ops and admins: one grievance by its ticket number, typed any way (case, spaces)."""
    if not can_handle_grievances(actor):
        raise ForbiddenError
    return _staff(await _service(request, db, clock).get(ticket_number))


@router.post("/ops/grievances/{ticket_number}/acknowledge", summary="Acknowledge a grievance")
async def acknowledge_grievance(
    ticket_number: str,
    body: GrievanceAcknowledgement,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> StaffGrievance:
    """Ops and admins: reply to the person (they see it). Audited. 409 INVALID_TRANSITION once
    acknowledged."""
    if not can_handle_grievances(actor):
        raise ForbiddenError
    view = await _service(request, db, clock).acknowledge(actor, ticket_number, reply=body.reply)
    return _staff(view)


@router.post("/ops/grievances/{ticket_number}/resolve", summary="Resolve a grievance")
async def resolve_grievance(
    ticket_number: str,
    body: GrievanceResolution,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> StaffGrievance:
    """Ops and admins: say what was done (the person sees it), acknowledging it too if it
    wasn't yet. Audited. 409 INVALID_TRANSITION once resolved."""
    if not can_handle_grievances(actor):
        raise ForbiddenError
    view = await _service(request, db, clock).resolve(
        actor, ticket_number, resolution=body.resolution
    )
    return _staff(view)
