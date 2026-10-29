"""Visit routes (ARCHITECTURE §11, §15; ADR 0033): students ask for visits and cancel their own,
ops book and cancel any, and field agents check in and record how theirs went. Another student's
visit, or another agent's, is a 404."""

import uuid
from datetime import timedelta
from typing import Annotated, Final

from fastapi import APIRouter, Query, Request, status

from app.core.clock import ClockDep
from app.core.current_actor import CurrentActor
from app.core.db import DbSession
from app.core.errors import ForbiddenError
from app.core.geometry import Point
from app.core.pagination import PageParams
from app.core.ratelimit import RateLimit, enforce
from app.modules.catalog.schemas import LatLng
from app.modules.visits.domain.visits import CancelledBy, Outcome, StudentVisitStatus, next_statuses
from app.modules.visits.policies import can_request_visits, can_run_visits, can_schedule_visits
from app.modules.visits.schemas import (
    StaffVisit,
    StaffVisitList,
    StaffVisitPage,
    StaffVisitPlace,
    StudentVisit,
    StudentVisitList,
    StudentVisitPlace,
    StudentVisitRequest,
    VisitCancelRequest,
    VisitCheckIn,
    VisitCheckInRequest,
    VisitOutcomeRequest,
    VisitPerson,
    VisitScheduleRequest,
)
from app.modules.visits.service import VisitService, VisitView

router = APIRouter(prefix="/v1", tags=["visits"])

# Asking is cheap for a student and costs ops a call: a few a day is plenty.
REQUESTS_PER_USER: Final = RateLimit("visit-requests-per-user", limit=10, window=timedelta(days=1))


def _service(request: Request, db: DbSession, clock: ClockDep) -> VisitService:
    return VisitService(db, clock, flags=request.app.state.flags)


def _student(view: VisitView) -> StudentVisit:
    visit = view.visit
    return StudentVisit(
        id=visit.public_id,
        status=StudentVisitStatus(visit.status),
        property=StudentVisitPlace(
            slug=view.place.slug, name=view.place.name, locality=view.place.locality
        ),
        preferred_starts=visit.preferred_starts,
        requested_at=visit.requested_at,
        scheduled_at=visit.scheduled_at,
        agent_name=None
        if view.agent is None or view.agent.name is None
        else view.agent.name.split()[0],
        checked_in=visit.checked_in_at is not None,
        outcome=None if visit.outcome is None else Outcome(visit.outcome),
        cancelled_at=visit.cancelled_at,
        cancelled_by=None if visit.cancelled_by is None else CancelledBy(visit.cancelled_by),
    )


def _staff(view: VisitView) -> StaffVisit:
    visit, place = view.visit, view.place
    check_in = None
    if (
        visit.checked_in_at is not None
        and view.position is not None
        and visit.check_in_accuracy_m is not None
        and visit.check_in_distance_m is not None
    ):
        check_in = VisitCheckIn(
            at=visit.checked_in_at,
            position=LatLng(lat=view.position.lat, lng=view.position.lng),
            accuracy_m=visit.check_in_accuracy_m,
            distance_m=visit.check_in_distance_m,
        )
    return StaffVisit(
        id=visit.public_id,
        status=StudentVisitStatus(visit.status),
        next_statuses=next_statuses(StudentVisitStatus(visit.status)),
        property=StaffVisitPlace(
            id=place.public_id,
            slug=place.slug,
            name=place.name,
            locality=place.locality,
            address_line=place.address_line,
            location=LatLng(lat=place.exact.lat, lng=place.exact.lng),
        ),
        student=VisitPerson(
            id=view.student.public_id, name=view.student.name, phone=view.student.phone_e164
        ),
        preferred_starts=visit.preferred_starts,
        requested_at=visit.requested_at,
        scheduled_at=visit.scheduled_at,
        agent=None
        if view.agent is None
        else VisitPerson(
            id=view.agent.public_id, name=view.agent.name, phone=view.agent.phone_e164
        ),
        check_in=check_in,
        outcome=None if visit.outcome is None else Outcome(visit.outcome),
        outcome_note=visit.outcome_note,
        finished_at=visit.finished_at,
        cancelled_at=visit.cancelled_at,
        cancelled_by=None if visit.cancelled_by is None else CancelledBy(visit.cancelled_by),
        cancel_reason=visit.cancel_reason,
    )


# Students.


@router.post("/visits", status_code=status.HTTP_201_CREATED, summary="Ask to visit a PG")
async def request_visit(
    body: StudentVisitRequest,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> StudentVisit:
    """Up to three times the student could come; ops call to book one. 422 VISIT_INVALID for
    times that don't work, 409 VISIT_EXISTS for a PG they've asked to see already, 409
    VISIT_LIMIT_REACHED with five visits open."""
    if not can_request_visits(actor):
        raise ForbiddenError
    await enforce(request.app.state.rate_limiter, REQUESTS_PER_USER, f"user:{actor.user_id}")
    view = await _service(request, db, clock).request(
        actor, body.property, body.starts, analytics_id=body.analytics_id
    )
    return _student(view)


@router.get("/visits", summary="Your visits")
async def my_visits(
    request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> StudentVisitList:
    """Newest first."""
    if not can_request_visits(actor):
        raise ForbiddenError
    return StudentVisitList(
        items=[_student(view) for view in await _service(request, db, clock).mine(actor)]
    )


@router.post("/visits/{visit_id}/cancel", summary="Cancel your visit")
async def cancel_my_visit(
    visit_id: uuid.UUID, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> StudentVisit:
    if not can_request_visits(actor):
        raise ForbiddenError
    return _student(await _service(request, db, clock).cancel_mine(actor, visit_id))


# Ops.


@router.get("/ops/visits", summary="Every visit")
async def ops_visits(
    request: Request,
    actor: CurrentActor,
    *,
    page: PageParams,
    db: DbSession,
    clock: ClockDep,
    visit_status: Annotated[StudentVisitStatus | None, Query(alias="status")] = None,
) -> StaffVisitPage:
    """Newest first, of one status if asked."""
    if not can_schedule_visits(actor):
        raise ForbiddenError
    found, next_cursor = await _service(request, db, clock).page(
        status=visit_status, cursor=page.after, limit=page.limit
    )
    return StaffVisitPage(items=[_staff(view) for view in found], next_cursor=next_cursor)


@router.get("/ops/visits/{visit_id}", summary="A visit, with its log")
async def ops_visit(
    visit_id: uuid.UUID, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> StaffVisit:
    if not can_schedule_visits(actor):
        raise ForbiddenError
    return _staff(await _service(request, db, clock).get(visit_id))


@router.post("/ops/visits/{visit_id}/schedule", summary="Book a visit's time and agent")
async def schedule_visit(
    visit_id: uuid.UUID,
    body: VisitScheduleRequest,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> StaffVisit:
    """Or change them. The student is texted the time and the address, and reminded."""
    if not can_schedule_visits(actor):
        raise ForbiddenError
    view = await _service(request, db, clock).schedule(
        actor, visit_id, at=body.at, agent=body.agent
    )
    return _staff(view)


@router.post("/ops/visits/{visit_id}/cancel", summary="Cancel a visit")
async def cancel_visit(
    visit_id: uuid.UUID,
    body: VisitCancelRequest,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> StaffVisit:
    if not can_schedule_visits(actor):
        raise ForbiddenError
    return _staff(await _service(request, db, clock).cancel(actor, visit_id, reason=body.reason))


# Field agents.


@router.get("/field/visits", summary="Your visits to run")
async def field_visits(
    request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> StaffVisitList:
    """From yesterday on, soonest first."""
    if not can_run_visits(actor):
        raise ForbiddenError
    return StaffVisitList(
        items=[_staff(view) for view in await _service(request, db, clock).assigned(actor)]
    )


@router.get("/field/visits/{visit_id}", summary="A visit you're to run")
async def field_visit(
    visit_id: uuid.UUID, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> StaffVisit:
    if not can_run_visits(actor):
        raise ForbiddenError
    return _staff(await _service(request, db, clock).assigned_one(actor, visit_id))


@router.post("/field/visits/{visit_id}/check-in", summary="Check in at the building")
async def check_in(
    visit_id: uuid.UUID,
    body: VisitCheckInRequest,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> StaffVisit:
    """The visit log: the time and where the agent's phone says they are. From two hours
    before the visit (409 CHECK_IN_TOO_EARLY before that)."""
    if not can_run_visits(actor):
        raise ForbiddenError
    view = await _service(request, db, clock).check_in(
        actor,
        visit_id,
        position=Point(lat=body.position.lat, lng=body.position.lng),
        accuracy_m=body.accuracy_m,
    )
    return _staff(view)


@router.post("/field/visits/{visit_id}/outcome", summary="Record how a visit went")
async def record_outcome(
    visit_id: uuid.UUID,
    body: VisitOutcomeRequest,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> StaffVisit:
    """After checking in (409 CHECK_IN_REQUIRED before)."""
    if not can_run_visits(actor):
        raise ForbiddenError
    view = await _service(request, db, clock).finish(
        actor, visit_id, outcome=body.outcome, note=body.note
    )
    return _staff(view)
