"""Verification routes (ARCHITECTURE §15, ADR 0024): ops book field agents' visits, and agents
report on them from the building.

Ops and admins book, cancel and read every visit, and suspend a verification. A field agent sees
only the visits booked for them, and reports only on those; anyone else's visit is a 404.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from app.core.clock import ClockDep
from app.core.current_actor import CurrentActor
from app.core.db import DbSession
from app.core.errors import ForbiddenError
from app.core.geometry import Point
from app.core.pagination import PageParams
from app.modules.catalog.domain.listing import PropertyStatus, VerificationStatus
from app.modules.catalog.domain.verification import Checklist, VisitResult, VisitStatus
from app.modules.catalog.policies import can_make_visits, can_manage_verification
from app.modules.catalog.router.listings import current_listing, lat_lng, media_info
from app.modules.catalog.schemas import (
    AgentInfo,
    FieldAgentList,
    ListingInfo,
    ListingLocality,
    Reason,
    ReportSubmit,
    VisitChecklist,
    VisitCreate,
    VisitInfo,
    VisitPage,
    VisitPlace,
)
from app.modules.catalog.service import Report, VerificationService, VisitReader, VisitView

router = APIRouter(prefix="/v1", tags=["catalog"])


def _managers(actor: CurrentActor) -> None:
    if not can_manage_verification(actor):
        raise ForbiddenError


def _service(request: Request, db: DbSession, clock: ClockDep) -> VerificationService:
    return VerificationService(db, clock, buckets=request.app.state.media_buckets)


def _reader(request: Request, db: DbSession) -> VisitReader:
    return VisitReader(
        db, buckets=request.app.state.media_buckets, storage=request.app.state.storage
    )


def _checklist_out(checklist: Checklist) -> VisitChecklist:
    return VisitChecklist(
        building_age_years=checklist.building_age_years,
        condition=checklist.condition,
        cracks=checklist.cracks,
        exits=checklist.exits,
        fire_extinguishers=checklist.fire_extinguishers,
        cctv=checklist.cctv,
        warden=checklist.warden,
        women_safety=sorted(checklist.women_safety),
        licence_number=checklist.licence_number,
        society_permission=checklist.society_permission,
        authority_notice=checklist.authority_notice,
    )


def _checklist_in(checklist: VisitChecklist) -> Checklist:
    return Checklist(
        building_age_years=checklist.building_age_years,
        condition=checklist.condition,
        cracks=checklist.cracks,
        exits=checklist.exits,
        fire_extinguishers=checklist.fire_extinguishers,
        cctv=checklist.cctv,
        warden=checklist.warden,
        women_safety=frozenset(checklist.women_safety),
        licence_number=checklist.licence_number,
        society_permission=checklist.society_permission,
        authority_notice=checklist.authority_notice,
    )


def _visit(view: VisitView) -> VisitInfo:
    visit, place = view.visit, view.property
    return VisitInfo(
        id=visit.public_id,
        status=VisitStatus(visit.status),
        scheduled_for=visit.scheduled_for,
        agent=None
        if view.agent is None
        else AgentInfo(id=view.agent.public_id, name=view.agent.name),
        property=VisitPlace(
            id=place.property.public_id,
            name=place.property.name,
            address_line=place.property.address_line,
            location=lat_lng(place.exact),
            locality=ListingLocality(slug=place.locality.slug, name=place.locality.name),
            owner_business_name=place.owner_business,
            owner_phone=place.owner_phone,
            verification_status=VerificationStatus(place.property.verification_status),
            status=PropertyStatus(place.property.status),
        ),
        submitted_at=visit.submitted_at,
        result=None if visit.result is None else VisitResult(visit.result),
        notes=visit.notes,
        position=None if view.position is None else lat_lng(view.position),
        accuracy_m=visit.position_accuracy_m,
        distance_m=visit.distance_m,
        checklist=None if view.checklist is None else _checklist_out(view.checklist),
        photos=[media_info(ref) for ref in view.photos],
        cancelled_at=visit.cancelled_at,
        cancel_reason=visit.cancel_reason,
    )


@router.get("/ops/field-agents", summary="Field agents, to book a visit for one")
async def field_agents(request: Request, actor: CurrentActor, db: DbSession) -> FieldAgentList:
    _managers(actor)
    found = await _reader(request, db).field_agents()
    return FieldAgentList(
        items=[AgentInfo(id=account.public_id, name=account.name) for account in found]
    )


@router.post(
    "/ops/properties/{property_id}/verification-visits",
    status_code=status.HTTP_201_CREATED,
    summary="Book a verification visit",
)
async def book_visit(
    property_id: uuid.UUID,
    body: VisitCreate,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> VisitInfo:
    """For an unverified, failed or suspended property, one visit at a time (409
    INVALID_TRANSITION otherwise). The property is then `scheduled`."""
    _managers(actor)
    visit = await _service(request, db, clock).schedule(
        actor, property_id, agent=body.agent, scheduled_for=body.scheduled_for
    )
    return _visit(await _reader(request, db).visit(visit.public_id))


@router.get("/ops/properties/{property_id}/verification-visits", summary="A property's visits")
async def property_visits(
    property_id: uuid.UUID, request: Request, actor: CurrentActor, page: PageParams, db: DbSession
) -> VisitPage:
    """Newest first."""
    _managers(actor)
    found, next_cursor = await _reader(request, db).of_property(property_id, page)
    return VisitPage(items=[_visit(view) for view in found], next_cursor=next_cursor)


@router.get("/ops/verification-visits", summary="Visits: an agent's own, or every one")
async def visits(
    request: Request,
    actor: CurrentActor,
    *,
    page: PageParams,
    db: DbSession,
    visit_status: Annotated[VisitStatus | None, Query(alias="status")] = None,
) -> VisitPage:
    """Soonest first. A field agent sees the visits booked for them; ops and admins see all."""
    if can_manage_verification(actor):
        agent_id = None
    elif can_make_visits(actor):
        agent_id = actor.user_id
    else:
        raise ForbiddenError
    found, next_cursor = await _reader(request, db).page(
        page, agent_id=agent_id, status=visit_status
    )
    return VisitPage(items=[_visit(view) for view in found], next_cursor=next_cursor)


@router.get("/ops/verification-visits/{visit_id}", summary="A visit, with its report")
async def visit(
    visit_id: uuid.UUID, request: Request, actor: CurrentActor, db: DbSession
) -> VisitInfo:
    if can_manage_verification(actor):
        agent_id = None
    elif can_make_visits(actor):
        agent_id = actor.user_id
    else:
        raise ForbiddenError
    return _visit(await _reader(request, db).visit(visit_id, agent_id=agent_id))


@router.post("/ops/verification-visits/{visit_id}/report", summary="Report on a visit")
async def report(
    visit_id: uuid.UUID,
    body: ReportSubmit,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> VisitInfo:
    """Only by the agent it was booked for. The property becomes `verified`, or `rejected` and
    paused if it was live. A building with a notice from the authorities can't pass (422
    LISTING_INVALID)."""
    if not can_make_visits(actor):
        raise ForbiddenError
    await _service(request, db, clock).submit(
        actor,
        visit_id,
        Report(
            checklist=_checklist_in(body.checklist),
            result=body.result,
            notes=body.notes,
            position=Point(lat=body.position.lat, lng=body.position.lng),
            accuracy_m=body.accuracy_m,
            photos=tuple(body.photos),
            move_pin=body.move_pin,
        ),
    )
    return _visit(await _reader(request, db).visit(visit_id))


@router.post("/ops/verification-visits/{visit_id}/cancel", summary="Cancel a booked visit")
async def cancel_visit(
    visit_id: uuid.UUID,
    body: Reason,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> VisitInfo:
    """The property's verification status goes back to what it was before the booking."""
    _managers(actor)
    await _service(request, db, clock).cancel(actor, visit_id, reason=body.reason)
    return _visit(await _reader(request, db).visit(visit_id))


@router.post(
    "/ops/properties/{property_id}/verification/suspend",
    summary="Suspend a property's verification",
)
async def suspend_verification(
    property_id: uuid.UUID,
    body: Reason,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> ListingInfo:
    """A complaint, or a notice from the authorities: a live listing is paused at once."""
    _managers(actor)
    await _service(request, db, clock).suspend(actor, property_id, reason=body.reason)
    return await current_listing(request, db, property_id)
