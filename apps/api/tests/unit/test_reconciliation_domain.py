"""Reconciliation's reading of a settlement report, line by line (step 6.6, ADR 0062)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.payments.domain.reconciliation import (
    GIVE_UP_AFTER,
    STUCK_AFTER,
    IssueKind,
    ItemReading,
    Ours,
    SettlementItem,
    is_stuck,
    read_item,
)

NOW = datetime(2026, 11, 6, 10, tzinfo=UTC)


def _item(kind: str = "payment", **change: object) -> SettlementItem:
    fields: dict[str, object] = {
        "entity_id": "pay_1",
        "kind": kind,
        "amount_paise": 200_000,
        "fee_paise": 4_720,
        "tax_paise": 720,
        "credit_paise": 195_280 if kind == "payment" else 0,
        "debit_paise": 200_000 if kind == "refund" else 0,
        "currency": "INR",
        "settled": True,
        "settlement_id": "setl_1",
        "payment_id": "pay_0" if kind == "refund" else None,
    } | change
    return SettlementItem(**fields)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("item", "ours", "reading"),
    [
        # A payment we captured: the fee kept, the rest paid to the bank.
        (
            _item(),
            Ours(200_000, done=True),
            ItemReading(None, fee_paise=4_720, settled_paise=195_280),
        ),
        # Not settled yet: the fee only, the payout when it comes.
        (_item(settled=False), Ours(200_000, done=True), ItemReading(None, fee_paise=4_720)),
        (_item(), None, ItemReading(IssueKind.UNKNOWN_PAYMENT)),
        (_item(), Ours(100, done=True), ItemReading(IssueKind.AMOUNT_MISMATCH)),
        (_item(), Ours(200_000, done=False), ItemReading(IssueKind.NOT_CAPTURED_HERE)),
        # A refund taken back out of a payout.
        (_item("refund"), Ours(200_000, done=True), ItemReading(None, refund_paise=200_000)),
        (_item("refund", settled=False), Ours(200_000, done=True), ItemReading(None)),
        (_item("refund"), None, ItemReading(IssueKind.UNKNOWN_REFUND)),
        (_item("refund"), Ours(100, done=True), ItemReading(IssueKind.AMOUNT_MISMATCH)),
        (
            _item("refund"),
            Ours(200_000, done=False),
            ItemReading(IssueKind.REFUND_NOT_PROCESSED_HERE),
        ),
        (_item("adjustment"), None, ItemReading(IssueKind.UNEXPECTED_ITEM)),
        (_item("transfer"), Ours(200_000, done=True), ItemReading(IssueKind.UNEXPECTED_ITEM)),
    ],
)
def test_each_line_of_a_report_comes_to_postings_or_an_issue(
    item: SettlementItem, ours: Ours | None, reading: ItemReading
) -> None:
    assert read_item(item, ours) == reading


@pytest.mark.parametrize(
    ("ago", "stuck"),
    [
        (STUCK_AFTER - timedelta(seconds=1), False),
        (STUCK_AFTER, True),
        (GIVE_UP_AFTER, True),
        (GIVE_UP_AFTER + timedelta(seconds=1), False),
    ],
)
def test_a_checkout_is_asked_about_once_it_should_be_back_until_nobody_will_pay(
    ago: timedelta, *, stuck: bool
) -> None:
    assert is_stuck(NOW - ago, NOW) is stuck
