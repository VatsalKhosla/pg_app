"""What a gateway's webhook says, and what's kept of it (step 6.2, ADR 0057), against the sample in
Razorpay's docs."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.modules.payments.adapters.razorpay import read_razorpay_webhook
from app.modules.payments.domain.payments import GatewayPayment, GatewayStatus
from app.modules.payments.domain.webhooks import (
    WEBHOOK_MAX_AGE,
    GatewayEvent,
    kept_payload,
    payment_in,
    too_old,
)

AT = datetime(2027, 7, 14, 10, 0, tzinfo=UTC)
# As Razorpay documents payment.captured, personal details and all.
CAPTURED: dict[str, Any] = {
    "entity": "event",
    "account_id": "acc_BFQ7uQEaa7j2z7",
    "event": "payment.captured",
    "contains": ["payment"],
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_DESlfW9H8K9uqM",
                "entity": "payment",
                "amount": 200000,
                "currency": "INR",
                "base_amount": 200000,
                "status": "captured",
                "order_id": "order_DESlLckIVRkHWj",
                "invoice_id": None,
                "international": False,
                "method": "upi",
                "amount_refunded": 0,
                "amount_transferred": 0,
                "refund_status": None,
                "captured": True,
                "description": None,
                "card_id": None,
                "bank": None,
                "wallet": None,
                "vpa": "a.student@okbank",
                "email": "a.student@example.com",
                "contact": "+919876543210",
                "notes": {"booking": "BK-7F3K2Q9M"},
                "fee": 4720,
                "tax": 720,
                "error_code": None,
                "error_description": None,
                "created_at": 1567674599,
            }
        }
    },
    "created_at": int(AT.timestamp()),
}


def _read(body: dict[str, Any]) -> GatewayEvent | None:
    return read_razorpay_webhook(json.dumps(body).encode())


def test_a_payment_event_says_which_payment_and_when() -> None:
    assert _read(CAPTURED) == GatewayEvent(
        "payment.captured",
        AT,
        GatewayPayment(
            "pay_DESlfW9H8K9uqM", "order_DESlLckIVRkHWj", 200_000, "INR", GatewayStatus.CAPTURED
        ),
    )


@pytest.mark.parametrize("kind", ["payment.authorized", "payment.failed", "order.paid"])
def test_each_event_acted_on_reads_the_same_way(kind: str) -> None:
    event = _read({**CAPTURED, "event": kind})
    assert event is not None
    assert event.kind == kind
    assert event.payment is not None


def test_nothing_personal_is_kept_and_what_is_kept_is_enough() -> None:
    event = _read(CAPTURED)
    assert event is not None

    kept = kept_payload(event)

    stored = json.dumps(kept)
    for personal in ("a.student", "+919876543210", "vpa", "email", "contact", "BK-7F3K2Q9M"):
        assert personal not in stored
    assert payment_in(kept) == event.payment


def test_an_event_we_dont_act_on_is_still_an_event_whatever_its_shape() -> None:
    body = {
        "event": "payment.downtime.started",
        "created_at": int(AT.timestamp()),
        "payload": {"payment.downtime": {"entity": {"id": "down_1"}}},
    }

    event = _read(body)

    assert event == GatewayEvent("payment.downtime.started", AT, None)
    assert event is not None
    assert kept_payload(event) == {"createdAt": AT.isoformat()}
    assert payment_in(kept_payload(event)) is None


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"payment": {}},
        {"payment": {"entity": {"id": "pay_1"}}},
        {
            "payment": {
                "entity": {"id": "pay_1", "amount": "1", "currency": "INR", "status": "new_kind"}
            }
        },
    ],
)
def test_a_payment_event_whose_payment_makes_no_sense_is_marked_not_dropped(
    payload: dict[str, Any],
) -> None:
    event = _read({**CAPTURED, "payload": payload})

    assert event == GatewayEvent("payment.captured", AT, None, unreadable=True)
    assert event is not None
    assert kept_payload(event)["unreadable"] is True


def test_a_payment_with_no_order_comes_back_from_storage_with_none() -> None:
    event = GatewayEvent(
        "payment.captured", AT, GatewayPayment("pay_1", None, 1, "INR", GatewayStatus.CAPTURED)
    )
    assert payment_in(kept_payload(event)) == event.payment


@pytest.mark.parametrize(
    "raw",
    [
        b"not json",
        b"[]",
        b"{}",
        b'{"event":"x"}',
        b'{"created_at":1}',
        b'{"event":1,"created_at":1}',
    ],
)
def test_what_isnt_an_event_at_all_is_none(raw: bytes) -> None:
    assert read_razorpay_webhook(raw) is None


def test_an_event_too_old_for_the_gateway_to_be_retrying_is_a_replay() -> None:
    event = GatewayEvent("payment.captured", AT, None)

    assert not too_old(event, AT)
    assert not too_old(event, AT + WEBHOOK_MAX_AGE)
    assert too_old(event, AT + WEBHOOK_MAX_AGE + timedelta(seconds=1))
