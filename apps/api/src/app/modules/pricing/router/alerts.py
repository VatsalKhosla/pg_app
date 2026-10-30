"""Pricing's integrity alerts (ARCHITECTURE §8.7 and §15; step 4.8, ADR 0043): ops and admins
read them and resolve them."""

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.core.clock import ClockDep
from app.core.current_actor import CurrentActor
from app.core.db import DbSession
from app.core.errors import ForbiddenError
from app.core.pagination import PageParams
from app.modules.pricing.domain.alerts import AlertKind
from app.modules.pricing.policies import can_manage_rule_sets
from app.modules.pricing.schemas import (
    AlertNumbers,
    AlertPlace,
    AlertResolution,
    AlertRoom,
    Changer,
    PricingAlertInfo,
    PricingAlertPage,
)
from app.modules.pricing.service import AlertService, AlertView

router = APIRouter(prefix="/v1/ops", tags=["pricing"])


def _ops(actor: CurrentActor) -> None:
    if not can_manage_rule_sets(actor):
        raise ForbiddenError


def _int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _info(view: AlertView) -> PricingAlertInfo:
    row, details = view.row, view.row.details
    place, room = details["property"], details.get("room")
    week = details.get("week")
    return PricingAlertInfo(
        id=row.public_id,
        kind=AlertKind(row.kind),
        property=AlertPlace(id=uuid.UUID(place["id"]), name=place["name"]),
        room=None if room is None else AlertRoom(id=uuid.UUID(room["id"]), label=room["label"]),
        numbers=AlertNumbers(
            listed_rent_paise=_int(details.get("listed_rent_paise")),
            median_rent_paise=_int(details.get("median_rent_paise")),
            comparables=_int(details.get("comparables")),
            locality=details.get("locality"),
            week=None if week is None else date.fromisoformat(week),
            quotes=_int(details.get("quotes")),
            clamped=_int(details.get("clamped")),
            activations=_int(details.get("activations")),
        ),
        raised_at=row.raised_at,
        resolved_at=row.resolved_at,
        resolved_by=None
        if view.resolved_by is None
        else Changer(id=view.resolved_by.public_id, name=view.resolved_by.name),
        resolution=row.resolution,
    )


@router.get("/pricing-alerts", summary="Pricing's integrity alerts")
async def pricing_alerts(
    *,
    actor: CurrentActor,
    page: PageParams,
    db: DbSession,
    clock: ClockDep,
    alert_status: Annotated[Literal["open", "resolved"], Query(alias="status")] = "open",
) -> PricingAlertPage:
    """Ops and admins: open alerts (or resolved ones), newest first. Each says what it's about
    and the numbers that raised it."""
    _ops(actor)
    items, next_cursor = await AlertService(db, clock).page(
        page, resolved=alert_status == "resolved"
    )
    return PricingAlertPage(items=[_info(item) for item in items], next_cursor=next_cursor)


@router.post("/pricing-alerts/{alert_id}/resolve", summary="Resolve an alert")
async def resolve_pricing_alert(
    alert_id: uuid.UUID,
    body: AlertResolution,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> PricingAlertInfo:
    """Ops and admins: they've looked at it, and say what they found. 409 INVALID_TRANSITION
    once it's resolved. Audited."""
    _ops(actor)
    return _info(await AlertService(db, clock).resolve(actor, alert_id, note=body.note))
