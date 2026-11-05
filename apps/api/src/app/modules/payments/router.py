"""Payment routes (ARCHITECTURE §9, §15; steps 6.1 and 6.2, ADRs 0056 and 0057): a student starts
paying their held booking's token, and tells us when checkout has finished, and the gateway tells us
what happened. Another student's is a 404."""

import uuid
from datetime import timedelta
from typing import Final

from fastapi import APIRouter, Request

from app.core.clock import ClockDep
from app.core.current_actor import CurrentActor
from app.core.db import DbSession
from app.core.errors import ForbiddenError
from app.core.ratelimit import RateLimit, enforce
from app.modules.payments.adapters.razorpay import EVENT_ID_HEADER, SIGNATURE_HEADER
from app.modules.payments.policies import can_pay
from app.modules.payments.schemas import (
    CheckoutCallback,
    CheckoutResult,
    PaymentStart,
    WebhookReceipt,
)
from app.modules.payments.service import PaymentWebhooks, TokenCheckout

router = APIRouter(prefix="/v1", tags=["payments"])

# Each start may make an order at the gateway. Someone paying in earnest needs a few tries.
STARTS_PER_USER: Final = RateLimit("payment-starts-per-user", limit=30, window=timedelta(hours=1))
# Each may ask the gateway about a payment. The browser asks again a few times while a bank
# finishes.
CHECKOUTS_PER_USER: Final = RateLimit("checkouts-per-user", limit=120, window=timedelta(hours=1))


def _checkout(request: Request, db: DbSession, clock: ClockDep) -> TokenCheckout:
    return TokenCheckout(db, clock, request.app.state.payment_gateway)


@router.post("/bookings/{code}/payment", summary="Start paying your booking's token")
async def start_token_payment(
    code: str, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> PaymentStart:
    """What the browser opens checkout with, for exactly the booking's token. A booking has one
    order, so asking again gets the same one, with no key needed. 409 INVALID_TRANSITION once the
    booking isn't waiting for its token; 503 PAYMENT_GATEWAY_UNAVAILABLE: try again."""
    if not can_pay(actor):
        raise ForbiddenError
    await enforce(request.app.state.rate_limiter, STARTS_PER_USER, f"user:{actor.user_id}")
    return await _checkout(request, db, clock).start(actor, code)


@router.post("/payments/{payment_id}/checkout-callback", summary="Checkout has finished")
async def checkout_callback(
    payment_id: uuid.UUID,
    body: CheckoutCallback,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> CheckoutResult:
    """Send what checkout handed the browser, as often as needed: a payment moves its booking
    once. 400 PAYMENT_SIGNATURE_INVALID for a signature the gateway didn't make; 409
    PAYMENT_MISMATCH for a payment that isn't this order's or its amount."""
    if not can_pay(actor):
        raise ForbiddenError
    await enforce(request.app.state.rate_limiter, CHECKOUTS_PER_USER, f"user:{actor.user_id}")
    return await _checkout(request, db, clock).finish(actor, payment_id, body)


@router.post("/payments/{payment_id}/test-checkout", summary="Pay at the test bank")
async def test_checkout(
    payment_id: uuid.UUID, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> CheckoutCallback:
    """With the fake gateway only, which moves no money and which production refuses: what a
    checkout that went through hands the browser, to send to the checkout callback. A 404 with a
    real gateway."""
    if not can_pay(actor):
        raise ForbiddenError
    return await _checkout(request, db, clock).test_checkout(actor, payment_id)


@router.post("/webhooks/razorpay", summary="What Razorpay tells us")
async def razorpay_webhook(request: Request, db: DbSession, clock: ClockDep) -> WebhookReceipt:
    """Razorpay's events, signed over the raw body: anyone may call this, and only a good signature
    gets anywhere. Each is stored once and answered at once, and a job does the work, so what
    Razorpay sends twice, or out of order, changes nothing twice. 400 WEBHOOK_INVALID otherwise."""
    return await PaymentWebhooks(db, clock).receive(
        request.app.state.payment_gateway,
        raw_body=await request.body(),
        signature=request.headers.get(SIGNATURE_HEADER, ""),
        event_id=request.headers.get(EVENT_ID_HEADER, ""),
    )
