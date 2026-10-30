"""Booking routes (ARCHITECTURE §7, §15; ADRs 0046, 0048): a student holds a bed with their quote
and sees their booking; its owner, or ops for them, sees it and confirms or rejects it. Another
student's booking, or another owner's, is a 404."""

from datetime import timedelta
from typing import Final

from fastapi import APIRouter, Request, Response, status

from app.core.clock import ClockDep
from app.core.current_actor import CurrentActor
from app.core.db import DbSession
from app.core.errors import ForbiddenError
from app.core.idempotency import OPENAPI_HEADER, StoredResponse, idempotent_request, replay
from app.core.ratelimit import RateLimit, enforce
from app.modules.booking.domain.state_machine import Party
from app.modules.booking.policies import can_answer_as_owner, can_book, can_run_bookings
from app.modules.booking.schemas import HoldRequest, ManagedBooking, RejectRequest, StudentBooking
from app.modules.booking.service import BookingDesk, BookingService

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


# Owners and ops: a booking with the token in waits for its owner's answer (step 5.4).


def _owner(actor: CurrentActor) -> Party:
    if not can_answer_as_owner(actor):
        raise ForbiddenError
    return Party.OWNER


def _ops(actor: CurrentActor) -> Party:
    if not can_run_bookings(actor):
        raise ForbiddenError
    return Party.OPS


@router.get("/owner/bookings/{code}", summary="A booking at one of your PGs")
async def owner_booking(
    code: str, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> ManagedBooking:
    return await BookingDesk(db, clock).view(actor, code, party=_owner(actor))


@router.post("/owner/bookings/{code}/confirm", summary="Confirm a booking at one of your PGs")
async def owner_confirm(
    code: str, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> ManagedBooking:
    """Once the token is in: the student hears it's confirmed, with the address. 409
    INVALID_TRANSITION otherwise."""
    return await BookingDesk(db, clock).confirm(actor, code, party=_owner(actor))


@router.post("/owner/bookings/{code}/reject", summary="Turn down a booking at one of your PGs")
async def owner_reject(
    code: str, body: RejectRequest, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> ManagedBooking:
    """Once the token is in: the bed is freed and the token refunded in full, and the student
    hears so. 409 INVALID_TRANSITION otherwise."""
    return await BookingDesk(db, clock).reject(actor, code, party=_owner(actor), reason=body.reason)


@router.get("/ops/bookings/{code}", summary="A booking")
async def ops_booking(
    code: str, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> ManagedBooking:
    return await BookingDesk(db, clock).view(actor, code, party=_ops(actor))


@router.post("/ops/bookings/{code}/confirm", summary="Confirm a booking for its owner")
async def ops_confirm(
    code: str, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> ManagedBooking:
    """As the owner's confirmation; audited as the ops member's."""
    return await BookingDesk(db, clock).confirm(actor, code, party=_ops(actor))


@router.post("/ops/bookings/{code}/reject", summary="Turn down a booking for its owner")
async def ops_reject(
    code: str, body: RejectRequest, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> ManagedBooking:
    """As the owner's rejection; audited as the ops member's, with the reason."""
    return await BookingDesk(db, clock).reject(actor, code, party=_ops(actor), reason=body.reason)
