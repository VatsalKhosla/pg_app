"""Booking routes (ARCHITECTURE §7, §15; ADR 0046): a student holds a bed with their quote, and
sees their booking. Another student's booking is a 404."""

from datetime import timedelta
from typing import Final

from fastapi import APIRouter, Request, Response, status

from app.core.clock import ClockDep
from app.core.current_actor import CurrentActor
from app.core.db import DbSession
from app.core.errors import ForbiddenError
from app.core.idempotency import OPENAPI_HEADER, StoredResponse, idempotent_request, replay
from app.core.ratelimit import RateLimit, enforce
from app.modules.booking.policies import can_book
from app.modules.booking.schemas import HoldRequest, StudentBooking
from app.modules.booking.service import BookingService

router = APIRouter(prefix="/v1", tags=["bookings"])

# A hold ties up a bed for its minutes, and someone booking in earnest needs a few at most.
HOLDS_PER_USER: Final = RateLimit("holds-per-user", limit=10, window=timedelta(hours=1))


def _service(request: Request, db: DbSession, clock: ClockDep) -> BookingService:
    return BookingService(db, clock, flags=request.app.state.flags)


@router.post(
    "/bookings",
    status_code=status.HTTP_201_CREATED,
    response_model=StudentBooking,
    summary="Hold a bed",
    openapi_extra=OPENAPI_HEADER,
)
async def hold_bed(
    body: HoldRequest, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> StudentBooking | Response:
    """With the student's own quote, unexpired, a bed of its room type held for the stay, at the
    quote's price, until the hold expires. Send an Idempotency-Key, the same on every retry: a
    retry gets the first answer back.

    - 409 BOOKING_NEEDS_VISIT while beds are reserved on visits only.
    - 409 QUOTE_EXPIRED or QUOTE_USED: ask for a new quote.
    - 409 HOLD_LIMIT_REACHED, and 409 BED_UNAVAILABLE when no bed is free for the stay.
    - 404 for a quote that isn't the student's own.
    """
    if not can_book(actor):
        raise ForbiddenError
    idempotent = await idempotent_request(request, scope=f"user:{actor.user_id}")
    await enforce(request.app.state.rate_limiter, HOLDS_PER_USER, f"user:{actor.user_id}")
    outcome = await _service(request, db, clock).hold(actor, body.quote, request=idempotent)
    return replay(outcome) if isinstance(outcome, StoredResponse) else outcome


@router.get("/bookings/{code}", summary="Your booking")
async def my_booking(
    code: str, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> StudentBooking:
    if not can_book(actor):
        raise ForbiddenError
    return await _service(request, db, clock).mine(actor, code)
