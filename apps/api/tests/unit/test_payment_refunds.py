"""What a refund is, and how much can go back (step 6.3, ADR 0059)."""

import json
import re
import uuid
from datetime import UTC, datetime

import pytest

from app.modules.payments.adapters.razorpay import read_razorpay_webhook
from app.modules.payments.domain.refunds import (
    GatewayRefund,
    GatewayRefundStatus,
    RefundStatus,
    from_gateway,
    needs_second_person,
    refund_of_receipt,
    refund_progress,
    refund_receipt,
    refundable,
)
from app.modules.payments.domain.webhooks import GatewayEvent, kept_payload, refund_in
from app.modules.payments.texts import REFUND_PROCESSED, TEMPLATES

S = RefundStatus
G = GatewayRefundStatus
AT = datetime(2027, 7, 14, 10, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("status", "seen", "after"),
    [
        (S.REQUESTED, G.PENDING, S.PENDING),
        (S.REQUESTED, G.PROCESSED, S.PROCESSED),
        (S.REQUESTED, G.FAILED, S.FAILED),
        (S.PENDING, G.PENDING, S.PENDING),
        (S.PENDING, G.PROCESSED, S.PROCESSED),
        (S.PENDING, G.FAILED, S.FAILED),
        # A slower answer can't take it back, and money that moved has moved.
        (S.PROCESSED, G.PENDING, S.PROCESSED),
        (S.PROCESSED, G.FAILED, S.PROCESSED),
        (S.FAILED, G.PENDING, S.FAILED),
        (S.FAILED, G.PROCESSED, S.PROCESSED),
        # A gateway has no say over a refund that never reached it.
        (S.AWAITING_APPROVAL, G.PROCESSED, S.AWAITING_APPROVAL),
        (S.DECLINED, G.PROCESSED, S.DECLINED),
    ],
)
def test_a_refund_only_moves_forward(status: S, seen: G, after: S) -> None:
    assert refund_progress(status, seen) is after


@pytest.mark.parametrize(
    ("seen", "status"),
    [(G.PENDING, S.PENDING), (G.PROCESSED, S.PROCESSED), (G.FAILED, S.FAILED)],
)
def test_a_refund_found_at_the_gateway_starts_where_it_says(seen: G, status: S) -> None:
    assert from_gateway(seen) is status


def test_only_what_didnt_go_back_can_go_back_again() -> None:
    assert refundable(200_000, []) == 200_000
    assert refundable(200_000, [(50_000, S.REQUESTED)]) == 150_000
    assert refundable(200_000, [(50_000, S.PENDING), (50_000, S.PROCESSED)]) == 100_000
    # Waiting for a second person, it's spoken for.
    assert refundable(200_000, [(150_000, S.AWAITING_APPROVAL)]) == 50_000
    assert refundable(200_000, [(200_000, S.FAILED), (200_000, S.DECLINED)]) == 200_000
    assert refundable(200_000, [(200_000, S.PROCESSED)]) == 0
    # A gateway's own refund can't leave less than nothing.
    assert refundable(200_000, [(200_000, S.PROCESSED), (1, S.PROCESSED)]) == 0


def test_a_second_person_only_above_the_threshold() -> None:
    assert not needs_second_person(499_999, 500_000)
    assert not needs_second_person(500_000, 500_000)
    assert needs_second_person(500_001, 500_000)


def test_a_receipt_fits_razorpays_limit_and_says_which_refund() -> None:
    public_id = uuid.uuid7()

    receipt = refund_receipt(public_id)

    assert len(receipt) <= 40
    assert receipt.isascii()
    assert refund_of_receipt(receipt) == public_id


@pytest.mark.parametrize("receipt", [None, "", "token-BK-7F3K2Q9M", "refund-not-hex", "Receipt 31"])
def test_a_receipt_that_isnt_ours_says_no_refund(receipt: str | None) -> None:
    assert refund_of_receipt(receipt) is None


def test_the_refund_text_has_the_blanks_its_sender_fills() -> None:
    assert set(re.findall(r"\{(\w+)\}", TEMPLATES[REFUND_PROCESSED])) == {"brand", "amount", "code"}


def _webhook(**refund: object) -> bytes:
    entity = {
        "id": "rfnd_FP8R8EGjGbPkVb",
        "entity": "refund",
        "amount": 200_000,
        "currency": "INR",
        "payment_id": "pay_29QQoUBi66xm2f",
        "notes": {"booking": "BK-7F3K2Q9M"},
        "receipt": "Receipt No. 31",
        "acquirer_data": {"arn": "10000000000000"},
        "created_at": 1597078914,
        "batch_id": None,
        "status": "processed",
        "speed_processed": "normal",
        "speed_requested": "normal",
    } | refund
    return json.dumps(
        {
            "entity": "event",
            "account_id": "acc_BFQ7uQEaa7j2z7",
            "event": "refund.processed",
            "contains": ["refund", "payment"],
            "payload": {
                "refund": {"entity": entity},
                "payment": {
                    "entity": {
                        "id": "pay_29QQoUBi66xm2f",
                        "amount": 200_000,
                        "currency": "INR",
                        "status": "refunded",
                        "order_id": "order_1",
                        "contact": "+919876543210",
                        "email": "a.student@example.com",
                    }
                },
            },
            "created_at": int(AT.timestamp()),
        }
    ).encode()


def test_a_refund_event_says_which_refund_and_keeps_nothing_personal() -> None:
    event = read_razorpay_webhook(_webhook())

    assert event is not None
    assert event.refund == GatewayRefund(
        "rfnd_FP8R8EGjGbPkVb",
        "pay_29QQoUBi66xm2f",
        200_000,
        G.PROCESSED,
        receipt="Receipt No. 31",
        reference="10000000000000",
    )
    assert event.payment is not None
    assert event.payment.order_id == "order_1"
    kept = kept_payload(event)
    assert refund_in(kept) == event.refund
    stored = json.dumps(kept)
    assert "a.student" not in stored
    assert "+919876543210" not in stored


@pytest.mark.parametrize(
    ("bank", "reference"),
    [
        ({"arn": None, "rrn": "rrn1", "utr": None}, "rrn1"),
        ({"utr": "utr1"}, "utr1"),
        ({}, None),
        (None, None),
    ],
)
def test_a_refund_quotes_whichever_reference_the_bank_gave(
    bank: dict[str, str] | None, reference: str | None
) -> None:
    event = read_razorpay_webhook(_webhook(acquirer_data=bank))

    assert event is not None
    assert event.refund is not None
    assert event.refund.reference == reference


def test_a_refund_event_without_its_payment_still_says_which_refund() -> None:
    body = json.loads(_webhook())
    del body["payload"]["payment"]

    event = read_razorpay_webhook(json.dumps(body).encode())

    assert event is not None
    assert event.payment is None
    assert event.refund is not None


def test_a_refund_event_whose_refund_makes_no_sense_is_marked_not_dropped() -> None:
    event = read_razorpay_webhook(_webhook(status="something_new"))

    assert event == GatewayEvent("refund.processed", AT, None, unreadable=True)
