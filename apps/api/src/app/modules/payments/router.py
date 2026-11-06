"""Payment routes (ARCHITECTURE §9, §15; steps 6.1 and 6.2, ADRs 0056 and 0057): a student starts
paying their held booking's token, and tells us when checkout has finished, and the gateway tells us
what happened. Another student's is a 404."""

import uuid
from datetime import timedelta
from typing import Annotated, Final

from fastapi import APIRouter, Query, Request, Response, status

from app.core.clock import ClockDep
from app.core.current_actor import CurrentActor
from app.core.db import DbSession
from app.core.errors import ForbiddenError, NotFoundError
from app.core.flags import Flag
from app.core.idempotency import OPENAPI_HEADER, StoredResponse, idempotent_request, replay
from app.core.pagination import PageParams
from app.core.ratelimit import RateLimit, enforce
from app.modules.payments.adapters.fake import FakeGateway
from app.modules.payments.adapters.razorpay import EVENT_ID_HEADER, SIGNATURE_HEADER
from app.modules.payments.domain.mandates import TokenMode
from app.modules.payments.domain.refunds import RefundStatus
from app.modules.payments.policies import can_pay, can_pay_invoices, can_reconcile, can_refund
from app.modules.payments.schemas import (
    CheckoutCallback,
    CheckoutResult,
    IssuePage,
    IssueResolution,
    IssueView,
    OpsPayments,
    OpsRefund,
    OpsRefundPage,
    PaymentStart,
    ReconciliationSummary,
    RefundDecline,
    RefundRequest,
    StudentPayments,
    WebhookReceipt,
)
from app.modules.payments.service import (
    InvoiceLinks,
    PaymentWebhooks,
    Reconciliation,
    Refunds,
    TokenCheckout,
)

router = APIRouter(prefix="/v1", tags=["payments"])

# Each start may make an order at the gateway. Someone paying in earnest needs a few tries.
STARTS_PER_USER: Final = RateLimit("payment-starts-per-user", limit=30, window=timedelta(hours=1))
# Each may ask the gateway about a payment. The browser asks again a few times while a bank
# finishes.
CHECKOUTS_PER_USER: Final = RateLimit("checkouts-per-user", limit=120, window=timedelta(hours=1))


def _ops(actor: CurrentActor) -> None:
    if not can_refund(actor):
        raise ForbiddenError


async def _checkout(request: Request, db: DbSession, clock: ClockDep) -> TokenCheckout:
    return TokenCheckout(
        db,
        clock,
        request.app.state.payment_gateway,
        token_mode=TokenMode(await request.app.state.flags.choice(Flag.TOKEN_MODE)),
        mandate_max_days=request.app.state.upi_mandate_max_days,
    )


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
    return await (await _checkout(request, db, clock)).start(actor, code)


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
    return await (await _checkout(request, db, clock)).finish(actor, payment_id, body)


@router.post("/payments/{payment_id}/test-checkout", summary="Pay at the test bank")
async def test_checkout(
    payment_id: uuid.UUID, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> CheckoutCallback:
    """With the fake gateway only, which moves no money and which production refuses: what a
    checkout that went through hands the browser, to send to the checkout callback. A 404 with a
    real gateway."""
    if not can_pay(actor):
        raise ForbiddenError
    return await (await _checkout(request, db, clock)).test_checkout(actor, payment_id)


@router.post("/payments/{payment_id}/mandate-check", summary="Is the block in?")
async def mandate_check(
    payment_id: uuid.UUID, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> CheckoutResult:
    """After the student authorised a block on their token (step 6.7), whatever checkout handed
    the browser: the gateway asked whether the mandate is confirmed, which alone moves the
    booking. Safe to repeat; 409 INVALID_TRANSITION for a token taken as a payment."""
    if not can_pay(actor):
        raise ForbiddenError
    await enforce(request.app.state.rate_limiter, CHECKOUTS_PER_USER, f"user:{actor.user_id}")
    return await (await _checkout(request, db, clock)).check_mandate(actor, payment_id)


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


@router.get("/bookings/{code}/payments", summary="What you paid for your booking")
async def my_booking_payments(
    code: str, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> StudentPayments:
    """What came in, and what's coming back."""
    if not can_pay(actor):
        raise ForbiddenError
    return StudentPayments(items=await Refunds(db, clock).for_student(actor, code))


@router.get("/ops/bookings/{code}/payments", summary="What a booking paid and got back")
async def ops_booking_payments(
    code: str, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> OpsPayments:
    _ops(actor)
    return OpsPayments(items=await Refunds(db, clock).for_ops(code))


@router.get("/ops/refunds", summary="Refunds")
async def ops_refunds(
    actor: CurrentActor,
    *,
    page: PageParams,
    db: DbSession,
    clock: ClockDep,
    refund_status: Annotated[RefundStatus | None, Query(alias="status")] = None,
) -> OpsRefundPage:
    """Oldest first, as a queue; of one status if asked."""
    _ops(actor)
    items, next_cursor = await Refunds(db, clock).page(page, status=refund_status)
    return OpsRefundPage(items=items, next_cursor=next_cursor)


@router.post(
    "/ops/payments/{payment_id}/refunds",
    status_code=status.HTTP_201_CREATED,
    response_model=OpsRefund,
    summary="Give money back",
    openapi_extra=OPENAPI_HEADER,
)
async def ops_refund(
    payment_id: uuid.UUID,
    body: RefundRequest,
    *,
    request: Request,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> OpsRefund | Response:
    """With a reason. Above the threshold it waits for a second person. Send an Idempotency-Key, the
    same on every retry. 409 REFUND_TOO_MUCH past what's left of the payment."""
    _ops(actor)
    idempotent = await idempotent_request(request, scope=f"user:{actor.user_id}")
    outcome = await Refunds(db, clock).request(
        actor,
        payment_id,
        amount_paise=body.amount_paise,
        reason=body.reason,
        second_person_above=request.app.state.refund_second_person_above_paise,
        request=idempotent,
    )
    return replay(outcome) if isinstance(outcome, StoredResponse) else outcome


@router.post("/ops/refunds/{refund_id}/approve", summary="Approve a refund as the second person")
async def ops_approve_refund(
    refund_id: uuid.UUID, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> OpsRefund:
    """409 REFUND_NEEDS_SECOND_PERSON for whoever asked for it."""
    _ops(actor)
    return await Refunds(db, clock).approve(actor, refund_id)


@router.post("/ops/refunds/{refund_id}/decline", summary="Decline a refund, with a reason")
async def ops_decline_refund(
    refund_id: uuid.UUID, body: RefundDecline, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> OpsRefund:
    """Nothing goes back. Whoever asked for it may withdraw it this way too."""
    _ops(actor)
    return await Refunds(db, clock).decline(actor, refund_id, reason=body.reason)


# Owners' invoices (step 6.5, ADR 0061).


@router.post(
    "/ops/invoices/{invoice_id}/payment-link",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ask for a new payment link",
)
async def ask_for_invoice_link(
    invoice_id: uuid.UUID, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> None:
    """After a link was cancelled or the gateway refused one: a job asks the gateway for another.
    409 INVALID_TRANSITION once the invoice is paid, or while a link can still be paid."""
    if not can_reconcile(actor):
        raise ForbiddenError
    await InvoiceLinks(db, clock).ask(actor, invoice_id)


@router.post("/owner/invoices/{invoice_id}/test-payment", summary="Pay an invoice at the test bank")
async def pay_invoice_at_test_bank(
    invoice_id: uuid.UUID, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> WebhookReceipt:
    """With the fake gateway only, which moves no money and which production refuses: the test bank
    pays the owner's own invoice's link, and tells us as Razorpay would, by a signed webhook. A 404
    with a real gateway."""
    if not can_pay_invoices(actor):
        raise ForbiddenError
    gateway = request.app.state.payment_gateway
    if not isinstance(gateway, FakeGateway):
        raise NotFoundError
    signed = await InvoiceLinks(db, clock).test_bank(gateway, actor, invoice_id)
    return await PaymentWebhooks(db, clock).receive(
        gateway, raw_body=signed.raw_body, signature=signed.signature, event_id=signed.event_id
    )


# Reconciliation (step 6.6, ADR 0062).


@router.get("/ops/reconciliation", summary="What's waiting on the gateway")
async def reconciliation_summary(
    actor: CurrentActor, db: DbSession, clock: ClockDep
) -> ReconciliationSummary:
    if not can_reconcile(actor):
        raise ForbiddenError
    return await Reconciliation(db, clock).summary()


@router.get("/ops/reconciliation/issues", summary="What reconciliation found")
async def reconciliation_issues(
    actor: CurrentActor,
    *,
    page: PageParams,
    db: DbSession,
    clock: ClockDep,
    open_only: Annotated[bool, Query(alias="open")] = True,
) -> IssuePage:
    """Newest first; only the open ones unless asked."""
    if not can_reconcile(actor):
        raise ForbiddenError
    items, next_cursor = await Reconciliation(db, clock).issues(page, open_only=open_only)
    return IssuePage(items=items, next_cursor=next_cursor)


@router.post(
    "/ops/reconciliation/issues/{issue_id}/resolve", summary="Close an issue with what was done"
)
async def resolve_reconciliation_issue(
    issue_id: uuid.UUID,
    body: IssueResolution,
    *,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
) -> IssueView:
    """409 INVALID_TRANSITION if it's closed already."""
    if not can_reconcile(actor):
        raise ForbiddenError
    return await Reconciliation(db, clock).resolve(actor, issue_id, resolution=body.resolution)
