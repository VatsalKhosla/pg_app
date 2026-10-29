"""Quotes (ARCHITECTURE §8.4 and §15; step 4.4, ADR 0039): anyone may ask what a room costs for
a move-in and a stay."""

import uuid
from datetime import date, timedelta
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from pydantic import TypeAdapter

from app.core.clock import ClockDep
from app.core.current_actor import OptionalActor
from app.core.db import DbSession
from app.core.ratelimit import RateLimit, rate_limited
from app.modules.catalog.schemas import Charge
from app.modules.pricing.domain.engine import ClampKind, RuleKind
from app.modules.pricing.schemas import (
    CalendarRoomInfo,
    CalendarWeekInfo,
    PriceCalendar,
    QuoteAdjustment,
    QuoteClamp,
    QuoteInfo,
    QuotePlace,
    QuoteRequest,
)
from app.modules.pricing.service import QuoteService, QuoteView

router = APIRouter(prefix="/v1", tags=["pricing"])

# A quote's charges, read back from the snapshot it keeps.
CHARGE: Final = TypeAdapter[Charge](Charge)
# Each quote is a few queries and a stored row: plenty for someone comparing rooms and dates.
QUOTES_PER_IP: Final = RateLimit("quotes-per-ip", limit=30, window=timedelta(minutes=1))
# The calendar (ADR 0040): twelve weekly move-ins by default, for an eleven-month stay, the
# common one; cached a little, as prices only move with rules, policies and bookings.
MAX_WEEKS: Final = 12
DEFAULT_STAY_MONTHS: Final = 11
CALENDAR_CACHE_CONTROL: Final = "public, max-age=300"
CALENDAR_PER_IP: Final = RateLimit("calendars-per-ip", limit=60, window=timedelta(minutes=1))
SLUG: Final = r"^[a-z0-9]+(-[a-z0-9]+)*$"


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
        charges=[CHARGE.validate_python(charge) for charge in row.mandatory_charges],
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


@router.get(
    "/properties/{slug}/price-calendar",
    summary="What each room costs for a move-in each week",
    dependencies=[Depends(rate_limited(CALENDAR_PER_IP))],
)
async def price_calendar(
    slug: Annotated[str, Path(pattern=SLUG, max_length=80)],
    *,
    request: Request,
    response: Response,
    db: DbSession,
    clock: ClockDep,
    start: Annotated[date | None, Query(alias="from")] = None,
    weeks: Annotated[int, Query(ge=1, le=MAX_WEEKS)] = MAX_WEEKS,
    stay: Annotated[int, Query(ge=1, le=36)] = DEFAULT_STAY_MONTHS,
) -> PriceCalendar:
    """Anyone, for a PG the public may see: each room's rent for a move-in each week from
    ``from`` (today at the earliest), 12 weeks by default, up to the booking horizon, as a quote
    would say for a ``stay``-month stay; and its free beds. Cached five minutes."""
    response.headers["Cache-Control"] = CALENDAR_CACHE_CONTROL
    view = await _service(request, db, clock).calendar(
        slug, start=start, weeks=weeks, stay_months=stay
    )
    return PriceCalendar(
        slug=view.property.slug,
        stay_months=view.stay_months,
        rooms=[
            CalendarRoomInfo(
                room_category=room.category.public_id,
                label=room.category.label,
                beds_free=room.beds_free,
                weeks=[
                    CalendarWeekInfo(
                        move_in=week.move_in, monthly_rent_paise=week.monthly_rent_paise
                    )
                    for week in room.weeks
                ],
            )
            for room in view.rooms
        ],
    )
