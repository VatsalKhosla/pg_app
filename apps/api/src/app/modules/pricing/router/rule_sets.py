"""PGs' pricing rule sets (ARCHITECTURE §15; step 4.3, ADR 0038): ops and admins draft, change
and activate them; owners get the same editor in Phase 7."""

import uuid
from typing import assert_never

from fastapi import APIRouter, Response, status

from app.core.clock import ClockDep
from app.core.current_actor import CurrentActor
from app.core.db import DbSession
from app.core.errors import ForbiddenError
from app.core.money import Paise
from app.modules.pricing.domain.engine import (
    EarlyBirdRule,
    LastMinuteRule,
    LengthOfStayRule,
    MonthDay,
    OccupancyRule,
    OccupancyTier,
    OverrideRule,
    RuleKind,
    RuleParams,
    SeasonRule,
    StayTier,
)
from app.modules.pricing.domain.rule_sets import RuleSetStatus
from app.modules.pricing.errors import RuleSetInvalidError
from app.modules.pricing.policies import can_manage_rule_sets
from app.modules.pricing.schemas import (
    Changer,
    EarlyBirdRuleParams,
    LastMinuteRuleParams,
    LengthOfStayRuleParams,
    OccupancyRuleParams,
    OccupancyRuleTier,
    OverrideRuleParams,
    PricingRuleInfo,
    PricingRuleInput,
    RuleCategory,
    RuleParamsBody,
    RuleSetActivation,
    RuleSetInfo,
    RuleSetList,
    RuleSetProperty,
    RuleSetSummaryInfo,
    SeasonRuleParams,
    StayRuleTier,
)
from app.modules.pricing.service import RuleDraft, RuleSetService, RuleSetView

router = APIRouter(prefix="/v1/ops", tags=["pricing"])


def _ops(actor: CurrentActor) -> None:
    if not can_manage_rule_sets(actor):
        raise ForbiddenError


def _params(body: RuleParamsBody) -> RuleParams:
    """The rule the body describes; 422 RULE_SET_INVALID for one that can't be."""
    try:
        match body:
            case SeasonRuleParams():
                return SeasonRule(MonthDay.parse(body.start), MonthDay.parse(body.end), body.bps)
            case OccupancyRuleParams():
                return OccupancyRule(
                    tuple(OccupancyTier(tier.min_occupancy_bps, tier.bps) for tier in body.tiers)
                )
            case EarlyBirdRuleParams():
                return EarlyBirdRule(body.min_days_before, body.bps)
            case LastMinuteRuleParams():
                return LastMinuteRule(body.max_days_before, body.max_occupancy_bps, body.bps)
            case LengthOfStayRuleParams():
                return LengthOfStayRule(
                    tuple(StayTier(tier.min_months, tier.bps) for tier in body.tiers)
                )
            case OverrideRuleParams():
                return OverrideRule(body.start, body.end, Paise(body.rent_paise))
            case _:
                assert_never(body)
    except ValueError as error:
        raise RuleSetInvalidError([str(error)]) from error


def _body(params: RuleParams) -> RuleParamsBody:
    match params:
        case SeasonRule():
            return SeasonRuleParams(
                kind="season", start=str(params.start), end=str(params.end), bps=params.bps
            )
        case OccupancyRule():
            return OccupancyRuleParams(
                kind="occupancy",
                tiers=[
                    OccupancyRuleTier(min_occupancy_bps=tier.min_occupancy_bps, bps=tier.bps)
                    for tier in params.tiers
                ],
            )
        case EarlyBirdRule():
            return EarlyBirdRuleParams(
                kind="early_bird", min_days_before=params.min_days_before, bps=params.bps
            )
        case LastMinuteRule():
            return LastMinuteRuleParams(
                kind="last_minute",
                max_days_before=params.max_days_before,
                max_occupancy_bps=params.max_occupancy_bps,
                bps=params.bps,
            )
        case LengthOfStayRule():
            return LengthOfStayRuleParams(
                kind="length_of_stay",
                tiers=[
                    StayRuleTier(min_months=tier.min_months, bps=tier.bps) for tier in params.tiers
                ],
            )
        case OverrideRule():
            return OverrideRuleParams(
                kind="override",
                start=params.start,
                end=params.end,
                rent_paise=params.rent_paise,
            )


def _draft(body: PricingRuleInput) -> RuleDraft:
    return RuleDraft(
        label=body.label,
        params=_params(body.params),
        room_categories=None if body.room_categories is None else frozenset(body.room_categories),
        enabled=body.enabled,
    )


def _info(view: RuleSetView) -> RuleSetInfo:
    found = view.rule_set
    activated_by = view.activated_by
    return RuleSetInfo(
        id=found.public_id,
        version=found.version,
        status=RuleSetStatus(found.status),
        property=RuleSetProperty(id=view.property.public_id, name=view.property.name),
        activated_at=found.activated_at,
        activated_by=None
        if activated_by is None
        else Changer(id=activated_by.public_id, name=activated_by.name),
        archived_at=found.archived_at,
        note=found.note,
        rules=[
            PricingRuleInfo(
                id=rule.row.public_id,
                position=rule.row.position,
                kind=RuleKind(rule.row.kind),
                label=rule.row.label,
                params=_body(rule.params),
                room_categories=None
                if rule.room_categories is None
                else [
                    RuleCategory(id=category.public_id, label=category.label)
                    for category in rule.room_categories
                ],
                enabled=rule.row.enabled,
            )
            for rule in view.rules
        ],
        problems=list(view.problems),
    )


@router.get("/properties/{property_id}/rule-sets", summary="A PG's pricing rule sets")
async def rule_sets(
    property_id: uuid.UUID, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> RuleSetList:
    """Ops and admins: every version, newest first: at most one draft and one active."""
    _ops(actor)
    place, sets = await RuleSetService(db, clock).sets(property_id)
    return RuleSetList(
        property=RuleSetProperty(id=place.public_id, name=place.name),
        items=[
            RuleSetSummaryInfo(
                id=found.rule_set.public_id,
                version=found.rule_set.version,
                status=RuleSetStatus(found.rule_set.status),
                activated_at=found.rule_set.activated_at,
                archived_at=found.rule_set.archived_at,
                note=found.rule_set.note,
                rules=found.rules,
            )
            for found in sets
        ],
    )


@router.post("/properties/{property_id}/rule-sets/draft", summary="Start a draft rule set")
async def start_draft(
    property_id: uuid.UUID, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> RuleSetInfo:
    """Ops and admins: the PG's draft, a copy of its set in force if it has to be made. Its
    ``problems`` say what would stop it being activated. Audited."""
    _ops(actor)
    return _info(await RuleSetService(db, clock).start_draft(actor, property_id))


@router.get("/rule-sets/{rule_set_id}", summary="A rule set with its rules")
async def rule_set(
    rule_set_id: uuid.UUID, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> RuleSetInfo:
    _ops(actor)
    return _info(await RuleSetService(db, clock).get(rule_set_id))


@router.post(
    "/rule-sets/{rule_set_id}/rules",
    status_code=status.HTTP_201_CREATED,
    summary="Add a rule to a draft",
)
async def add_rule(
    rule_set_id: uuid.UUID,
    body: PricingRuleInput,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> RuleSetInfo:
    """Ops and admins: a rule at the end of the draft. 422 RULE_SET_INVALID for one that can't
    be; 409 INVALID_TRANSITION for a set that isn't a draft. Audited."""
    _ops(actor)
    return _info(await RuleSetService(db, clock).add_rule(actor, rule_set_id, _draft(body)))


@router.put("/rules/{rule_id}", summary="Change a draft's rule")
async def replace_rule(
    rule_id: uuid.UUID, body: PricingRuleInput, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> RuleSetInfo:
    _ops(actor)
    return _info(await RuleSetService(db, clock).replace_rule(actor, rule_id, _draft(body)))


@router.delete("/rules/{rule_id}", summary="Remove a draft's rule")
async def remove_rule(
    rule_id: uuid.UUID, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> RuleSetInfo:
    _ops(actor)
    return _info(await RuleSetService(db, clock).remove_rule(actor, rule_id))


@router.post("/rule-sets/{rule_set_id}/activate", summary="Put a draft in force")
async def activate(
    rule_set_id: uuid.UUID,
    body: RuleSetActivation,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> RuleSetInfo:
    """Ops and admins: the draft goes into force and the set before it is archived, in one
    step. Nothing priced before moves (rule 5). 422 RULE_SET_INVALID names every problem.
    Audited."""
    _ops(actor)
    return _info(await RuleSetService(db, clock).activate(actor, rule_set_id, note=body.note))


@router.delete(
    "/rule-sets/{rule_set_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Discard a draft",
)
async def discard(
    rule_set_id: uuid.UUID, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> Response:
    """Ops and admins: a draft only; sets that were in force are kept. Audited."""
    _ops(actor)
    await RuleSetService(db, clock).discard(actor, rule_set_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
