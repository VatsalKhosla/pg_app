"""UPI one-time mandates (step 6.7, ADR 0064): how long a block has to last, when one is taken at
all, what a booking that ends keeps of it, and the Razorpay adapter's calls and token events."""

import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.core.calendar import INDIA
from app.modules.payments.adapters.fake import FakeGateway
from app.modules.payments.adapters.razorpay import RazorpayGateway, read_razorpay_webhook
from app.modules.payments.domain.mandates import (
    PRE_DEBIT_NOTICE,
    MandatePayer,
    MandateStatus,
    kept_on_release,
    mandate_expiry,
    mandate_fits,
)
from app.modules.payments.domain.webhooks import kept_payload, mandate_in
from app.modules.payments.errors import PaymentGatewayRefusedError

NOW = datetime(2026, 11, 6, 10, tzinfo=UTC)
PAYER = MandatePayer("A Student", "+919000000000")


def test_a_block_lasts_past_the_last_move_in_day_the_check_and_the_notice() -> None:
    expires = mandate_expiry(date(2026, 12, 1), no_show_days=2, check_window_hours=24)

    # The last day a student may still move in is 3 December; it ends at midnight in India.
    assert expires == datetime(2026, 12, 4, tzinfo=INDIA) + timedelta(
        hours=24
    ) + PRE_DEBIT_NOTICE + timedelta(days=1)


@pytest.mark.parametrize(
    ("days", "fits"), [(30, True), (90, True), (91, False), (0, False), (-1, False)]
)
def test_a_block_is_taken_only_for_as_long_as_banks_take_one(days: int, *, fits: bool) -> None:
    assert mandate_fits(NOW, NOW + timedelta(days=days), max_days=90) is fits


@pytest.mark.parametrize(
    ("token", "refund", "kept"),
    [
        (200_000, 200_000, 0),
        (200_000, 250_000, 0),
        (200_000, 50_000, 150_000),
        (200_000, 0, 200_000),
    ],
)
def test_a_booking_that_ends_keeps_only_what_doesnt_go_back(
    token: int, refund: int, kept: int
) -> None:
    assert kept_on_release(token, refund) == kept


def _gateway(handler: Any) -> RazorpayGateway:
    return RazorpayGateway(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        key_id="rzp_test_abc",
        key_secret=SecretStr("a-secret"),
        webhook_secret=SecretStr("a-webhook-secret"),
        retry_delay_s=0,
    )


def test_a_mandate_order_blocks_exactly_the_token_for_the_students_customer() -> None:
    sent: list[tuple[str, str, dict[str, Any]]] = []

    def answer(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        sent.append((request.method, request.url.path, body))
        if request.url.path.endswith("/customers"):
            return httpx.Response(200, json={"id": "cust_1"})
        return httpx.Response(
            200, json={"id": "order_1", "amount": 200_000, "currency": "INR", "receipt": "token-x"}
        )

    expires = NOW + timedelta(days=40)
    order = asyncio.run(
        _gateway(answer).create_mandate(
            amount_paise=200_000, expires_at=expires, receipt="token-x", payer=PAYER, notes={}
        )
    )

    assert (order.order_id, order.customer_id, order.amount_paise) == ("order_1", "cust_1", 200_000)
    customer, created = sent
    assert customer[1] == "/v1/customers"
    assert customer[2] == {"name": "A Student", "contact": "+919000000000", "fail_existing": "0"}
    assert created[2]["method"] == "upi"
    assert created[2]["customer_id"] == "cust_1"
    assert created[2]["token"] == {
        "max_amount": 200_000,
        "expire_at": int(expires.timestamp()),
        "frequency": "one_time",
    }


def test_a_debit_gives_notice_then_charges_the_mandate_and_a_release_cancels_it() -> None:
    sent: list[tuple[str, str, dict[str, Any]]] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append((request.method, request.url.path, json.loads(request.content or b"{}")))
        if request.url.path.endswith("/payments/create/recurring"):
            return httpx.Response(200, json={"razorpay_payment_id": "pay_9"})
        if request.url.path.endswith("/cancel"):
            return httpx.Response(200, json={"status": "cancellation_initiated"})
        return httpx.Response(200, json={"id": "order_9", "amount": 200_000, "currency": "INR"})

    gateway = _gateway(answer)
    after = NOW + PRE_DEBIT_NOTICE

    async def scenario() -> str:
        await gateway.order_debit(
            mandate_id="token_1", amount_paise=200_000, receipt="debit-x", after=after, notes={}
        )
        paid = await gateway.debit(
            order_id="order_9",
            customer_id="cust_1",
            mandate_id="token_1",
            amount_paise=200_000,
            payer=PAYER,
            notes={},
        )
        await gateway.release_mandate(customer_id="cust_1", mandate_id="token_1")
        return paid

    assert asyncio.run(scenario()) == "pay_9"
    order, debit, release = sent
    assert order[2]["notification"] == {
        "token_id": "token_1",
        "payment_after": int(after.timestamp()),
    }
    assert order[2]["payment_capture"] is True
    assert debit[1] == "/v1/payments/create/recurring"
    assert {key: debit[2][key] for key in ("order_id", "customer_id", "token", "amount")} == {
        "order_id": "order_9",
        "customer_id": "cust_1",
        "token": "token_1",
        "amount": 200_000,
    }
    assert release[:2] == ("PUT", "/v1/customers/cust_1/tokens/token_1/cancel")


def test_a_refused_debit_is_final_and_a_mandate_is_read_from_the_customers_tokens() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={"items": [{"id": "token_1", "recurring_details": {"status": "confirmed"}}]},
            )
        return httpx.Response(
            400, json={"error": {"code": "BAD_REQUEST_ERROR", "description": "Token expired"}}
        )

    gateway = _gateway(answer)
    with pytest.raises(PaymentGatewayRefusedError):
        asyncio.run(
            gateway.debit(
                order_id="o",
                customer_id="c",
                mandate_id="token_1",
                amount_paise=1,
                payer=PAYER,
                notes={},
            )
        )
    found = asyncio.run(gateway.fetch_mandate(customer_id="c", mandate_id="token_1"))
    gone = asyncio.run(gateway.fetch_mandate(customer_id="c", mandate_id="token_9"))

    assert found.status is MandateStatus.CONFIRMED
    # Razorpay leaves out what lapsed or was used: nothing is left blocked by it.
    assert gone.status is MandateStatus.CANCELLED


def test_a_token_event_reads_as_razorpay_sends_it_and_keeps_nothing_personal() -> None:
    signed = FakeGateway().mandate_webhook(
        "token.confirmed", "token_1", MandateStatus.CONFIRMED, at=NOW
    )

    event = read_razorpay_webhook(signed.raw_body)

    assert event is not None
    assert event.mandate is not None
    kept = kept_payload(event)
    assert mandate_in(kept) == event.mandate
    assert "fakebank" not in json.dumps(kept)
