"""Booking routes (ARCHITECTURE §7, §15; ADRs 0046, 0048 to 0051): a student holds a bed with their
quote, sees their booking, says when they've moved in, and reports a room that isn't as shown;
its owner, or ops for them, sees it and confirms or rejects it; ops settle reports. Another
student's booking, or another owner's, is a 404."""

import uuid
from datetime import timedelta
from typing import Annotated, Final

from fastapi import APIRouter, Query, Request, Response, status

from app.core.clock import ClockDep
from app.core.current_actor import CurrentActor
from app.core.db import DbSession
from app.core.errors import ForbiddenError
from app.core.idempotency import OPENAPI_HEADER, StoredResponse, idempotent_request, replay
from app.core.pagination import PageParams
from app.core.ratelimit import RateLimit, enforce
from app.modules.booking.domain.disputes import DisputeStatus
from app.modules.booking.domain.state_machine import Party
from app.modules.booking.policies import can_answer_as_owner, can_book, can_run_bookings
from app.modules.booking.schemas import (
    CancelRequest,
    DisputeRequest,
    HoldRequest,
    ManagedBooking,
    MoveInReminder,
    OpsDispute,
    OpsDisputePage,
    RejectRequest,
    ResolveRequest,
    StudentBooking,
    StudentBookingList,
)
from app.modules.booking.service import BookingDesk, BookingService, Disputes

router = APIRouter(prefix="/v1", tags=["bookings"])

# A hold ties up a bed for its minutes, and someone booking in earnest needs a few at most.
HOLDS_PER_USER: Final = RateLimit("holds-per-user", limit=10, window=timedelta(hours=1))


def _service(request: Request, db: DbSession, clock: ClockDep) -> BookingService:
    return BookingService(
        db, clock, flags=request.app.state.flags, buckets=request.app.state.media_buckets
    )


def _disputes(request: Request, db: DbSession, clock: ClockDep) -> Disputes:
    return Disputes(
        db, clock, buckets=request.app.state.media_buckets, storage=request.app.state.storage
    )


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


@router.get("/bookings", summary="Your bookings")
async def my_bookings(
    request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> StudentBookingList:
    """Newest first."""
    if not can_book(actor):
        raise ForbiddenError
    return StudentBookingList(items=await _service(request, db, clock).my_bookings(actor))


@router.post("/bookings/{code}/cancel", summary="Cancel your booking")
async def cancel_my_booking(
    code: str,
    body: CancelRequest,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> StudentBooking:
    """With the refund the student was shown (the booking's ``cancellation``): free until the
    cutoff, then as the late-cancel rule says. 409 REFUND_CHANGED if cancelling now means
    something else; 409 INVALID_TRANSITION once it can't be cancelled."""
    if not can_book(actor):
        raise ForbiddenError
    return await _service(request, db, clock).cancel(actor, code, refund_paise=body.refund_paise)


@router.post("/bookings/{code}/check-in", summary="Say you've moved in")
async def check_in(
    code: str, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> StudentBooking:
    """On a confirmed booking, from the day before the move-in: the student's 24 hours to tell us
    if the room isn't as shown start now, and the owner hears. 409 INVALID_TRANSITION otherwise."""
    if not can_book(actor):
        raise ForbiddenError
    return await _service(request, db, clock).check_in(actor, code)


@router.post("/bookings/{code}/disputes", summary="Report that your room isn't as shown")
async def open_dispute(
    code: str,
    body: DisputeRequest,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> StudentBooking:
    """Inside the student's time to check the room, once they've moved in: why, in their own
    words, with up to six of their own dispute photos, ready. The booking waits for ops, and the
    owner hears. 409 INVALID_TRANSITION outside that time; 422 DISPUTE_INVALID for photos that
    aren't theirs or aren't ready."""
    if not can_book(actor):
        raise ForbiddenError
    return await _service(request, db, clock).dispute(
        actor, code, reason=body.reason, description=body.description, photos=body.photos
    )


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


@router.post(
    "/ops/bookings/{code}/move-in-reminder", summary="Ask a student to say they've moved in"
)
async def ops_move_in_reminder(
    code: str, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> MoveInReminder:
    """When ops hear a student has moved in but they haven't said so: the student gets a text
    asking them to, one a day at most. The booking doesn't change, as the check window starts on
    the student's own word. 409 INVALID_TRANSITION unless they may check in now."""
    _ops(actor)
    return MoveInReminder(sent=await BookingDesk(db, clock).move_in_reminder(actor, code))


# Ops: students' reports that their room isn't as shown (step 5.7).


@router.get("/ops/disputes", summary="Reports that a room isn't as shown")
async def ops_disputes(
    request: Request,
    actor: CurrentActor,
    *,
    page: PageParams,
    db: DbSession,
    clock: ClockDep,
    dispute_status: Annotated[DisputeStatus | None, Query(alias="status")] = None,
) -> OpsDisputePage:
    """Oldest first, as a queue; of one status if asked."""
    _ops(actor)
    items, next_cursor = await _disputes(request, db, clock).page(page, status=dispute_status)
    return OpsDisputePage(items=items, next_cursor=next_cursor)


@router.get("/ops/disputes/{dispute_id}", summary="A report that a room isn't as shown")
async def ops_dispute(
    dispute_id: uuid.UUID, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> OpsDispute:
    """The student's words and photos (links signed for five minutes), the booking, and the
    student's phone to call them."""
    _ops(actor)
    return await _disputes(request, db, clock).view(dispute_id)


@router.post("/ops/disputes/{dispute_id}/resolve", summary="Settle a report")
async def ops_resolve_dispute(
    dispute_id: uuid.UUID,
    body: ResolveRequest,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> OpsDispute:
    """Refund: the bed is released, the token refunded in full, and the student offered PGs like
    it. Uphold: the stay goes ahead and the token is earned. Both text the student and the owner;
    the notes stay on the record. 409 INVALID_TRANSITION once it's settled."""
    _ops(actor)
    return await _disputes(request, db, clock).resolve(
        actor, dispute_id, outcome=body.outcome, notes=body.notes
    )
