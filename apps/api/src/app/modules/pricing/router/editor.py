"""Ops' pricing editor (ARCHITECTURE §8.6 and §15; step 4.6, ADR 0041): any rule set version's
prices before it's in force, from the same inputs and engine as a quote, and the market a PG's
rents sit in. Owners get the same editor in Phase 7."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.core.clock import ClockDep
from app.core.current_actor import CurrentActor
from app.core.db import DbSession
from app.core.errors import ForbiddenError
from app.modules.pricing.domain.policies import BandSource
from app.modules.pricing.domain.quotes import DEFAULT_STAY_MONTHS, MAX_STAY_MONTHS
from app.modules.pricing.policies import can_manage_rule_sets
from app.modules.pricing.router.quotes import CHARGE, MAX_WEEKS
from app.modules.pricing.schemas import (
    MarketBand,
    MarketCaps,
    MarketRoomInfo,
    PricingMarket,
    PricingPreview,
    QuoteAdjustment,
    QuoteClamp,
    RuleSetCalendar,
    RuleSetProperty,
    RuleSetRoomInfo,
    RuleSetWeekInfo,
)
from app.modules.pricing.service import QuoteService

router = APIRouter(prefix="/v1/ops", tags=["pricing"])

type Stay = Annotated[int, Query(ge=1, le=MAX_STAY_MONTHS)]


def _service(request: Request, db: DbSession, clock: ClockDep) -> QuoteService:
    return QuoteService(db, clock, flags=request.app.state.flags, beds=request.app.state.beds_taken)


def _ops(actor: CurrentActor) -> None:
    if not can_manage_rule_sets(actor):
        raise ForbiddenError


@router.get("/rule-sets/{rule_set_id}/preview", summary="Price a room with a rule set's rules")
async def preview(
    rule_set_id: uuid.UUID,
    *,
    room: uuid.UUID,
    move_in: Annotated[date, Query(alias="moveIn")],
    actor: CurrentActor,
    request: Request,
    db: DbSession,
    clock: ClockDep,
    stay: Stay = DEFAULT_STAY_MONTHS,
) -> PricingPreview:
    """Ops and admins, for any version, draft or not: what a quote made today for an active
    room of the PG would say were it in force, with the owner's fee. Move-ins up to a year
    ahead, beyond the booking horizon (``bookableFrom`` says when students can quote it). 422
    QUOTE_INVALID for a move-in or stay that can't be priced, or a room whose bounds leave no
    rent. Nothing is stored."""
    _ops(actor)
    view = await _service(request, db, clock).preview(
        rule_set_id, room, move_in=move_in, stay_months=stay
    )
    result, category = view.quote, view.category
    return PricingPreview(
        rule_set=rule_set_id,
        room_category=category.public_id,
        room_category_label=category.label,
        move_in=move_in,
        stay_months=stay,
        base_rent_paise=result.base_rent_paise,
        monthly_rent_paise=result.monthly_rent_paise,
        premium_bps=result.premium_bps,
        discount_bps=result.discount_bps,
        adjustments=[
            QuoteAdjustment(
                kind=item.kind, label=item.label, bps=item.bps, rent_paise=item.rent_paise
            )
            for item in result.adjustments
        ],
        clamps=[
            QuoteClamp(kind=item.kind, asked=item.asked, allowed=item.allowed)
            for item in result.clamps
        ],
        explanation=view.explanation,
        token_paise=result.token_paise,
        due_at_move_in_paise=result.due_at_move_in_paise,
        deposit_paise=category.security_deposit,
        charges=[CHARGE.validate_python(charge) for charge in view.charges],
        monthly_charges_paise=view.monthly_charges,
        one_time_charges_paise=view.one_time_charges,
        fee_paise=result.fee_paise,
        gst_paise=result.gst_paise,
        owner_fee_total_paise=result.owner_fee_total_paise,
        bookable_from=view.bookable_from,
    )


@router.get(
    "/rule-sets/{rule_set_id}/calendar", summary="Each room's rent by move-in with a rule set"
)
async def rule_set_calendar(
    rule_set_id: uuid.UUID,
    *,
    actor: CurrentActor,
    request: Request,
    db: DbSession,
    clock: ClockDep,
    start: Annotated[date | None, Query(alias="from")] = None,
    weeks: Annotated[int, Query(ge=1, le=MAX_WEEKS)] = MAX_WEEKS,
    stay: Stay = DEFAULT_STAY_MONTHS,
) -> RuleSetCalendar:
    """Ops and admins, for any version: each active room's rent for a move-in each week from
    ``from`` (today at the earliest), 12 weeks by default, up to a year ahead, were it in force,
    with the limits that held each week's rent back; and the room's free beds."""
    _ops(actor)
    view = await _service(request, db, clock).set_calendar(
        rule_set_id, start=start, weeks=weeks, stay_months=stay
    )
    return RuleSetCalendar(
        rule_set=rule_set_id,
        stay_months=view.stay_months,
        rooms=[
            RuleSetRoomInfo(
                room_category=room.category.public_id,
                label=room.category.label,
                base_rent_paise=room.category.base_rent,
                beds_free=room.beds_free,
                weeks=[
                    RuleSetWeekInfo(
                        move_in=week.move_in,
                        monthly_rent_paise=week.monthly_rent_paise,
                        clamps=list(week.clamps),
                    )
                    for week in room.weeks
                ],
            )
            for room in view.rooms
        ],
    )


@router.get("/properties/{property_id}/market", summary="The band and market beside a PG's rents")
async def market(
    property_id: uuid.UUID, actor: CurrentActor, request: Request, db: DbSession, clock: ClockDep
) -> PricingMarket:
    """Ops and admins: for each of the PG's active rooms, its listed rent and the owner's
    bounds beside the band in force for its locality and occupancy, and the middle of the rents
    the locality's other published PGs list for that occupancy; and the caps in force."""
    _ops(actor)
    view = await _service(request, db, clock).market(property_id)
    return PricingMarket(
        property=RuleSetProperty(id=view.property.public_id, name=view.property.name),
        locality=view.locality,
        caps=MarketCaps(
            max_premium_bps=view.caps.max_premium_bps,
            max_discount_bps=view.caps.max_discount_bps,
            rounding_step_paise=view.caps.rounding_step_paise,
        ),
        rooms=[
            MarketRoomInfo(
                room_category=room.category.public_id,
                label=room.category.label,
                occupancy=room.category.occupancy,
                base_rent_paise=room.category.base_rent,
                owner_min_paise=room.category.owner_min,
                owner_max_paise=room.category.owner_max,
                band=None
                if room.band is None
                else MarketBand(
                    min_rent_paise=room.band.min_rent_paise,
                    max_rent_paise=room.band.max_rent_paise,
                    source=BandSource(room.band.source),
                    reference=room.band.reference,
                ),
                median_rent_paise=room.median_rent,
                comparables=room.comparables,
            )
            for room in view.rooms
        ],
    )
