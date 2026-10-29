"""Quotes (ARCHITECTURE §8.4 and §15; step 4.4, ADR 0039): anyone may ask what a room costs for
a move-in and a stay."""

import uuid
from datetime import timedelta
from typing import Final

from fastapi import APIRouter, Depends, Request, status

from app.core.clock import ClockDep
from app.core.current_actor import OptionalActor
from app.core.db import DbSession
from app.core.ratelimit import RateLimit, rate_limited
from app.modules.pricing.domain.engine import ClampKind, RuleKind
from app.modules.pricing.schemas import (
    QuoteAdjustment,
    QuoteCharge,
    QuoteClamp,
    QuoteInfo,
    QuotePlace,
    QuoteRequest,
)
from app.modules.pricing.service import QuoteService, QuoteView

router = APIRouter(prefix="/v1", tags=["pricing"])

# Each quote is a few queries and a stored row: plenty for someone comparing rooms and dates.
QUOTES_PER_IP: Final = RateLimit("quotes-per-ip", limit=30, window=timedelta(minutes=1))


def _service(request: Request, db: DbSession, clock: ClockDep) -> QuoteService:
    return QuoteService(db, clock, flags=request.app.state.flags, beds=request.app.state.beds_taken)


def _info(view: QuoteView) -> QuoteInfo:
    row = view.row
    return QuoteInfo(
        id=row.public_id,
        place=QuotePlace(
            slug=view.property.slug,
            name=view.property.name,
            room_category=view.category.public_id,
            room_category_label=view.category.label,
        ),
        move_in=row.move_in,
        stay_months=row.stay_months,
        base_rent_paise=row.base_rent_paise,
        monthly_rent_paise=row.monthly_rent_paise,
        adjustments=[
            QuoteAdjustment(
                kind=RuleKind(str(item["kind"])),
                label=str(item["label"]),
                bps=None if item["bps"] is None else int(str(item["bps"])),
                rent_paise=None if item["rent_paise"] is None else int(str(item["rent_paise"])),
            )
            for item in row.adjustments
        ],
        clamps=[
            QuoteClamp(
                kind=ClampKind(str(item["kind"])),
                asked=int(str(item["asked"])),
                allowed=int(str(item["allowed"])),
            )
            for item in row.clamps
        ],
        explanation=row.explanation,
        token_paise=row.token_paise,
        due_at_move_in_paise=row.due_at_move_in_paise,
        deposit_paise=row.deposit_paise,
        charges=[QuoteCharge.model_validate(charge) for charge in row.mandatory_charges],
        monthly_charges_paise=row.monthly_charges_paise,
        one_time_charges_paise=row.one_time_charges_paise,
        expires_at=row.expires_at,
        expired=view.expired,
    )


@router.post(
    "/quotes",
    status_code=status.HTTP_201_CREATED,
    summary="Price a room for a move-in and a stay",
    dependencies=[Depends(rate_limited(QUOTES_PER_IP))],
)
async def create_quote(
    body: QuoteRequest, request: Request, actor: OptionalActor, db: DbSession, clock: ClockDep
) -> QuoteInfo:
    """Anyone, for a room in a PG the public may see: the monthly rent, fixed for the whole
    stay, with how it was worked out, the token, the deposit and the mandatory charges. It
    stands for 30 minutes. 422 QUOTE_INVALID for a move-in or stay that can't be quoted; 404
    for a room the public can't see; 30 a minute per address."""
    view = await _service(request, db, clock).create(
        actor, body.room_category, move_in=body.move_in, stay_months=body.stay_months
    )
    return _info(view)


@router.get("/quotes/{quote_id}", summary="A quote")
async def get_quote(
    quote_id: uuid.UUID, request: Request, db: DbSession, clock: ClockDep
) -> QuoteInfo:
    """Anyone with its id: a quote holds no personal data. ``expired`` once its 30 minutes are
    up."""
    return _info(await _service(request, db, clock).get(quote_id))
