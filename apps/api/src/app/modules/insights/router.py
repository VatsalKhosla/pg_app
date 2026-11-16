"""Insights routes (ARCHITECTURE §15; step 7.6, ADR 0063): an owner's numbers for one of their
PGs. Anyone else's PG is a 404."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.core.clock import ClockDep
from app.core.current_actor import CurrentActor
from app.core.db import DbSession
from app.core.errors import ForbiddenError
from app.modules.insights.domain.insights import MAX_DAYS, MAX_WEEKS
from app.modules.insights.domain.owner import MAX_MONTHS, MIN_MONTHS
from app.modules.insights.policies import can_see_ops_insights, can_see_own_insights
from app.modules.insights.schemas import OpsInsights, OwnerOverview, PropertyInsights
from app.modules.insights.service import OpsDashboard, OwnerInsights, OwnerOverviewService
from app.modules.pricing.service import QuoteService

router = APIRouter(prefix="/v1", tags=["insights"])


@router.get("/owner/overview", summary="Your business at a glance")
async def my_overview(
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
    months: Annotated[int, Query(ge=MIN_MONTHS, le=MAX_MONTHS)] = 12,
) -> OwnerOverview:
    """Every one of your PGs' beds today; the tenants we placed, month by month for the last
    ``months`` months (this one included), with the rent their stays were booked at; our fees;
    and what waits for you: bookings to answer and the week's visits."""
    if not can_see_own_insights(actor):
        raise ForbiddenError
    return await OwnerOverviewService(db, clock).of(actor, months=months)


@router.get("/owner/properties/{property_id}/insights", summary="How your PG is doing")
async def my_insights(
    property_id: uuid.UUID,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
    days: Annotated[int, Query(ge=1, le=MAX_DAYS)] = 30,
) -> PropertyInsights:
    """The last ``days`` days, today included: page views, visits asked for and bookings made;
    how full it is today; and each room's listed rent beside the middle of its locality's."""
    if not can_see_own_insights(actor):
        raise ForbiddenError
    quotes = QuoteService(
        db, clock, flags=request.app.state.flags, beds=request.app.state.beds_taken
    )
    return await OwnerInsights(db, clock, quotes).of(actor, property_id, days=days)


@router.get("/ops/insights", summary="The business at a glance")
async def ops_insights(
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
    weeks: Annotated[int, Query(ge=4, le=MAX_WEEKS)] = 12,
) -> OpsInsights:
    """Each of the last ``weeks`` weeks: tokens secured, visits asked for and placement fees
    invoiced; listings by status; and the bookings board's counts."""
    if not can_see_ops_insights(actor):
        raise ForbiddenError
    return await OpsDashboard(db, clock).of(weeks=weeks)
