"""Payment links (step 6.5, ADR 0061): what the gateway's word about one comes to, its webhooks as
Razorpay sends them, and the Razorpay adapter's calls for links, attempts, refunds and settlement
reports (step 6.6, ADR 0062)."""

import asyncio
import json
import uuid
from datetime import UTC, date, datetime
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.modules.payments.adapters.fake import FakeGateway
from app.modules.payments.adapters.razorpay import RazorpayGateway, read_razorpay_webhook
from app.modules.payments.domain.links import (
    GatewayLink,
    LinkReading,
    LinkStatus,
    link_reference,
    read_link,
)
from app.modules.payments.domain.payments import INR, GatewayPayment, GatewayStatus
from app.modules.payments.domain.webhooks import kept_payload, link_in, payment_in
from app.modules.payments.errors import (
    PaymentGatewayRefusedError,
    PaymentGatewayUnavailableError,
)

AT = datetime(2026, 11, 6, 10, tzinfo=UTC)
LINK = GatewayLink("plink_1", "inv-x", 154_000, 154_000, LinkStatus.PAID, "https://rzp.io/i/x")
PAID = GatewayPayment("pay_1", "order_1", 154_000, INR, GatewayStatus.CAPTURED)


def _gateway(handler: Any) -> RazorpayGateway:
    return RazorpayGateway(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        key_id="rzp_test_abc",
        key_secret=SecretStr("a-secret"),
        webhook_secret=SecretStr("a-webhook-secret"),
        retry_delay_s=0,
    )


def _link_body(**change: Any) -> dict[str, Any]:
    return {
        "id": "plink_1",
        "reference_id": "inv-x",
        "amount": 154_000,
        "amount_paid": 0,
        "status": "created",
        "short_url": "https://rzp.io/i/x",
        "payments": None,
    } | change


def test_a_reference_fits_razorpays_forty_characters() -> None:
    reference = link_reference(uuid.uuid4())
    assert reference.startswith("inv-")
    assert len(reference) <= 40


@pytest.mark.parametrize(
    ("link", "payment", "reading"),
    [
        (LINK, PAID, LinkReading.PAID),
        (LINK, None, LinkReading.MISMATCH),
        (
            GatewayLink("plink_1", None, 154_000, 100, LinkStatus.PAID, ""),
            PAID,
            LinkReading.MISMATCH,
        ),
        (
            LINK,
            GatewayPayment("pay_1", None, 100, INR, GatewayStatus.CAPTURED),
            LinkReading.MISMATCH,
        ),
        (
            LINK,
            GatewayPayment("pay_1", None, 154_000, "USD", GatewayStatus.CAPTURED),
            LinkReading.MISMATCH,
        ),
        (
            LINK,
            GatewayPayment("pay_1", None, 154_000, INR, GatewayStatus.AUTHORIZED),
            LinkReading.MISMATCH,
        ),
        (GatewayLink("plink_1", None, 154_000, 0, LinkStatus.EXPIRED, ""), None, LinkReading.ENDED),
        (
            GatewayLink("plink_1", None, 154_000, 0, LinkStatus.CANCELLED, ""),
            None,
            LinkReading.ENDED,
        ),
        (
            GatewayLink("plink_1", None, 154_000, 0, LinkStatus.CREATED, ""),
            None,
            LinkReading.NOTHING_YET,
        ),
        (
            GatewayLink("plink_1", None, 154_000, 100, LinkStatus.PARTIALLY_PAID, ""),
            PAID,
            LinkReading.NOTHING_YET,
        ),
    ],
)
def test_only_exactly_the_balance_captured_in_rupees_pays_a_link(
    link: GatewayLink, payment: GatewayPayment | None, reading: LinkReading
) -> None:
    assert read_link(link, payment, amount_paise=154_000) is reading


def test_a_paid_links_webhook_reads_as_razorpay_sends_it_and_keeps_nothing_personal() -> None:
    fake = FakeGateway()
    made = asyncio.run(
        fake.create_payment_link(
            amount_paise=154_000, reference="inv-abc", description="Invoice", notes={}
        )
    )
    signed = fake.link_paid(made.id, reference="inv-abc", at=AT)
    assert fake.verify_webhook(raw_body=signed.raw_body, signature=signed.signature)
    event = fake.read_webhook(signed.raw_body)
    assert event is not None
    assert event.link is not None
    assert (event.kind, event.link.status, event.link.amount_paid_paise) == (
        "payment_link.paid",
        LinkStatus.PAID,
        154_000,
    )
    kept = kept_payload(event)
    assert link_in(kept) == event.link
    found = payment_in(kept)
    assert found is not None
    assert found.id == event.link.payment_id
    assert "+91" not in json.dumps(kept)


def test_an_ended_link_has_no_payment_and_an_unreadable_one_is_kept_for_a_person() -> None:
    fake = FakeGateway()
    ended = GatewayLink("plink_fake_100_ab", None, 100, 0, LinkStatus.EXPIRED, "")
    event = read_razorpay_webhook(fake.link_webhook("payment_link.expired", ended, at=AT).raw_body)
    assert event is not None
    assert (event.payment, event.link) == (None, ended)
    broken = fake.signed({"event": "payment_link.paid", "created_at": 1, "payload": {}})
    unreadable = read_razorpay_webhook(broken.raw_body)
    assert unreadable is not None
    assert unreadable.unreadable


def test_a_link_is_for_the_exact_balance_and_razorpay_sends_no_message_of_its_own() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        assert request.url.path == "/v1/payment_links"
        return httpx.Response(200, json=_link_body())

    link = asyncio.run(
        _gateway(handler).create_payment_link(
            amount_paise=154_000, reference="inv-x", description="Invoice", notes={"a": "b"}
        )
    )
    assert (link.id, link.url, link.status) == ("plink_1", "https://rzp.io/i/x", LinkStatus.CREATED)
    assert seen[0]["amount"] == 154_000
    assert seen[0]["accept_partial"] is False
    assert seen[0]["notify"] == {"sms": False, "email": False}


def test_a_reference_used_before_finds_the_link_it_made() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                400,
                json={
                    "error": {
                        "code": "BAD_REQUEST_ERROR",
                        "description": "payment link creation with reference ID already attempted",
                    }
                },
            )
        assert request.url.params["reference_id"] == "inv-x"
        return httpx.Response(
            200,
            json={"payment_links": [_link_body(reference_id="inv-x2"), _link_body()]},
        )

    link = asyncio.run(
        _gateway(handler).create_payment_link(
            amount_paise=154_000, reference="inv-x", description="Invoice", notes={}
        )
    )
    assert link.reference == "inv-x"


def test_a_reference_spent_on_nothing_and_a_refusal_are_final() -> None:
    def spent(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(400, json={"error": {"description": "duplicate request"}})
        return httpx.Response(200, json={"payment_links": []})

    def refused(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"description": "payment links are off"}})

    for handler in (spent, refused):
        with pytest.raises(PaymentGatewayRefusedError):
            asyncio.run(
                _gateway(handler).create_payment_link(
                    amount_paise=154_000, reference="inv-x", description="Invoice", notes={}
                )
            )


def test_a_gateway_in_trouble_making_a_link_is_tried_again_later() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"description": "down"}})

    with pytest.raises(PaymentGatewayUnavailableError):
        asyncio.run(
            _gateway(handler).create_payment_link(
                amount_paise=154_000, reference="inv-x", description="Invoice", notes={}
            )
        )


def test_a_fetched_link_names_the_payment_that_paid_it() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/payment_links/plink_1"
        return httpx.Response(
            200,
            json=_link_body(
                status="paid",
                amount_paid=154_000,
                payments=[{"payment_id": "pay_1", "status": "captured"}],
            ),
        )

    link = asyncio.run(_gateway(handler).fetch_payment_link("plink_1"))
    assert (link.status, link.payment_id) == (LinkStatus.PAID, "pay_1")


def test_an_orders_attempts_and_a_payments_refunds_are_read() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/orders/order_1/payments":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "pay_1",
                            "order_id": "order_1",
                            "amount": 200_000,
                            "currency": "INR",
                            "status": "failed",
                        },
                        {
                            "id": "pay_2",
                            "order_id": "order_1",
                            "amount": 200_000,
                            "currency": "INR",
                            "status": "captured",
                        },
                    ]
                },
            )
        assert request.url.path == "/v1/payments/pay_2/refunds"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "rfnd_1",
                        "payment_id": "pay_2",
                        "amount": 200_000,
                        "status": "processed",
                        "receipt": "r",
                    }
                ]
            },
        )

    gateway = _gateway(handler)
    attempts = asyncio.run(gateway.order_payments("order_1"))
    refunds = asyncio.run(gateway.payment_refunds("pay_2"))
    assert [each.status for each in attempts] == [GatewayStatus.FAILED, GatewayStatus.CAPTURED]
    assert [each.id for each in refunds] == ["rfnd_1"]


def test_a_days_settlement_report_is_read_a_thousand_lines_at_a_time() -> None:
    asked: list[dict[str, str]] = []
    line = {
        "entity_id": "pay_1",
        "type": "payment",
        "amount": 200_000,
        "fee": 4_720,
        "tax": 720,
        "credit": 195_280,
        "debit": 0,
        "currency": "INR",
        "settled": True,
        "settlement_id": "setl_1",
        "payment_id": None,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(dict(request.url.params))
        count = 1_000 if request.url.params["skip"] == "0" else 2
        return httpx.Response(200, json={"items": [line] * count})

    items = asyncio.run(_gateway(handler).settlement_items(date(2026, 11, 5)))
    assert len(items) == 1_002
    assert asked[0] | {"skip": "x"} == {
        "year": "2026",
        "month": "11",
        "day": "05",
        "count": "1000",
        "skip": "x",
    }
    assert [each["skip"] for each in asked] == ["0", "1000"]
    first = items[0]
    assert (first.fee_paise, first.credit_paise, first.settled) == (4_720, 195_280, True)


def test_reads_the_gateway_refuses_are_failures_that_pass() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"description": "bad key"}})

    gateway = _gateway(handler)
    for call in (
        gateway.fetch_payment_link("plink_1"),
        gateway.order_payments("order_1"),
        gateway.payment_refunds("pay_1"),
        gateway.settlement_items(date(2026, 11, 5)),
    ):
        with pytest.raises(PaymentGatewayUnavailableError):
            asyncio.run(call)


def test_the_fake_gateway_says_only_what_its_told() -> None:
    fake = FakeGateway()
    link = asyncio.run(
        fake.create_payment_link(amount_paise=500, reference="inv-y", description="", notes={})
    )
    assert asyncio.run(fake.fetch_payment_link(link.id)).status is LinkStatus.CREATED
    assert asyncio.run(fake.order_payments("order_x")) == []
    assert asyncio.run(fake.payment_refunds("pay_x")) == []
    assert asyncio.run(fake.settlement_items(date(2026, 11, 5))) == []
    fake.refuses_links = True
    with pytest.raises(PaymentGatewayRefusedError):
        asyncio.run(
            fake.create_payment_link(amount_paise=500, reference="inv-z", description="", notes={})
        )
    with pytest.raises(PaymentGatewayUnavailableError):
        fake.link_paid("plink_somebody_elses", reference=None, at=AT)
