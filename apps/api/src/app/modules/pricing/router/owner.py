"""Owners' own pricing editor (ARCHITECTURE §8.6, §15; step 7.4, ADR 0063): the editor ops use, for
an owner's own PGs, with the caps, the band and the locality's middle rent beside each room, and a
preview before anything goes into force. Anyone else's PG, set or rule is a 404. Owners' changes
face the same caps and bands as anyone's (rule 6), and nothing priced before moves (rule 5)."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, status

from app.core.clock import ClockDep
from app.core.current_actor import CurrentActor
from app.core.db import DbSession
from app.core.errors import ForbiddenError, NotFoundError
from app.modules.pricing.domain.quotes import DEFAULT_STAY_MONTHS, MAX_STAY_MONTHS
from app.modules.pricing.policies import can_price_own_pgs
from app.modules.pricing.router.editor import _calendar, _market, _preview, _service
from app.modules.pricing.router.quotes import MAX_WEEKS
from app.modules.pricing.router.rule_sets import _draft, _info, _set_list
from app.modules.pricing.schemas import (
    PricingMarket,
    PricingPreview,
    PricingRuleInput,
    RuleSetActivation,
    RuleSetCalendar,
    RuleSetInfo,
    RuleSetList,
)
from app.modules.pricing.service import RuleSetService

router = APIRouter(prefix="/v1/owner", tags=["pricing"])

type Stay = Annotated[int, Query(ge=1, le=MAX_STAY_MONTHS)]


async def _own(
    actor: CurrentActor,
    sets: RuleSetService,
    *,
    property_id: uuid.UUID | None = None,
    rule_set_id: uuid.UUID | None = None,
    rule_id: uuid.UUID | None = None,
) -> None:
    if not can_price_own_pgs(actor):
        raise ForbiddenError
    if not await sets.owned_by(
        actor.user_id, property_id=property_id, rule_set_id=rule_set_id, rule_id=rule_id
    ):
        raise NotFoundError


@router.get("/properties/{property_id}/rule-sets", summary="Your PG's pricing rule sets")
async def my_rule_sets(
    property_id: uuid.UUID, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> RuleSetList:
    """Every version, newest first: at most one draft and one in force."""
    sets = RuleSetService(db, clock)
    await _own(actor, sets, property_id=property_id)
    return _set_list(*await sets.sets(property_id))


@router.post("/properties/{property_id}/rule-sets/draft", summary="Start a draft rule set")
async def my_draft(
    property_id: uuid.UUID, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> RuleSetInfo:
    """The PG's draft, a copy of its set in force if it has to be made. Audited."""
    sets = RuleSetService(db, clock)
    await _own(actor, sets, property_id=property_id)
    return _info(await sets.start_draft(actor, property_id))


@router.get("/rule-sets/{rule_set_id}", summary="A rule set of yours, with its rules")
async def my_rule_set(
    rule_set_id: uuid.UUID, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> RuleSetInfo:
    sets = RuleSetService(db, clock)
    await _own(actor, sets, rule_set_id=rule_set_id)
    return _info(await sets.get(rule_set_id))


@router.post(
    "/rule-sets/{rule_set_id}/rules",
    status_code=status.HTTP_201_CREATED,
    summary="Add a rule to your draft",
)
async def my_new_rule(
    rule_set_id: uuid.UUID,
    body: PricingRuleInput,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> RuleSetInfo:
    """422 RULE_SET_INVALID for a rule that can't be; 409 INVALID_TRANSITION for a set that
    isn't a draft. Audited."""
    sets = RuleSetService(db, clock)
    await _own(actor, sets, rule_set_id=rule_set_id)
    return _info(await sets.add_rule(actor, rule_set_id, _draft(body)))


@router.put("/rules/{rule_id}", summary="Change your draft's rule")
async def my_rule_change(
    rule_id: uuid.UUID, body: PricingRuleInput, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> RuleSetInfo:
    sets = RuleSetService(db, clock)
    await _own(actor, sets, rule_id=rule_id)
    return _info(await sets.replace_rule(actor, rule_id, _draft(body)))


@router.delete("/rules/{rule_id}", summary="Remove your draft's rule")
async def my_rule_removal(
    rule_id: uuid.UUID, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> RuleSetInfo:
    sets = RuleSetService(db, clock)
    await _own(actor, sets, rule_id=rule_id)
    return _info(await sets.remove_rule(actor, rule_id))


@router.post("/rule-sets/{rule_set_id}/activate", summary="Put your draft in force")
async def my_activation(
    rule_set_id: uuid.UUID,
    body: RuleSetActivation,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> RuleSetInfo:
    """The draft goes into force and the set before it is archived. Nothing priced before moves
    (rule 5). 422 RULE_SET_INVALID names every problem. Audited."""
    sets = RuleSetService(db, clock)
    await _own(actor, sets, rule_set_id=rule_set_id)
    return _info(await sets.activate(actor, rule_set_id, note=body.note))


@router.delete(
    "/rule-sets/{rule_set_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Discard your draft",
)
async def my_discard(
    rule_set_id: uuid.UUID, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> Response:
    sets = RuleSetService(db, clock)
    await _own(actor, sets, rule_set_id=rule_set_id)
    await sets.discard(actor, rule_set_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/rule-sets/{rule_set_id}/preview", summary="Price a room of yours with a rule set")
async def my_preview(
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
    """What a quote made today would say were the set in force, with the fee you'd pay.
    Nothing is stored."""
    await _own(actor, RuleSetService(db, clock), rule_set_id=rule_set_id)
    view = await _service(request, db, clock).preview(
        rule_set_id, room, move_in=move_in, stay_months=stay
    )
    return _preview(rule_set_id, view, move_in=move_in, stay=stay)


@router.get("/properties/{property_id}/market", summary="Your rents beside the locality's")
async def my_market(
    property_id: uuid.UUID, actor: CurrentActor, request: Request, db: DbSession, clock: ClockDep
) -> PricingMarket:
    """For each room: its listed rent and your bounds, the band in force, the middle of the
    rents the locality's other PGs list, and the caps."""
    await _own(actor, RuleSetService(db, clock), property_id=property_id)
    return _market(await _service(request, db, clock).market(property_id))


@router.get(
    "/rule-sets/{rule_set_id}/calendar", summary="Each of your rooms' rent by move-in with a set"
)
async def my_calendar(
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
    """Each active room's rent for a move-in each week, were the set in force, with the limits
    that held a week's rent back; and the room's free beds."""
    await _own(actor, RuleSetService(db, clock), rule_set_id=rule_set_id)
    view = await _service(request, db, clock).set_calendar(
        rule_set_id, start=start, weeks=weeks, stay_months=stay
    )
    return _calendar(rule_set_id, view)
