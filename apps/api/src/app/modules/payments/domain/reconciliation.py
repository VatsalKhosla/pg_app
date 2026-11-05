"""Reconciliation: checking our payments against the gateway's word (ARCHITECTURE §9.6; step 6.6,
ADR 0062). Pure.

- **Every 15 minutes:** a payment still waiting, a refund still on its way, or a link still unpaid,
  is asked about at the gateway, and what it says goes through the same path as a webhook would.
- **Daily:** the gateway's settlement report, item by item, against what we hold: what it kept as
  its fee, what it paid our bank, and what it took back for refunds are posted, and anything that
  doesn't match becomes an issue for ops.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

# A checkout that hasn't come back in this long gets asked about, early enough to secure its
# booking inside the 15-minute hold...
STUCK_AFTER: Final = timedelta(minutes=5)
# ...for this long, after which nobody is going to pay it.
GIVE_UP_AFTER: Final = timedelta(days=3)
# A payment the bank said yes to but nobody captured.
AUTHORIZED_TOO_LONG: Final = timedelta(hours=1)
# A refund the gateway has had this long and not sent.
REFUND_TOO_LONG: Final = timedelta(days=7)
# Razorpay settles in two working days; a week covers holidays.
UNSETTLED_TOO_LONG: Final = timedelta(days=7)
# How many of each kind one run asks the gateway about, so a run stays short.
CHECKS_PER_RUN: Final = 50


class ItemKind(StrEnum):
    PAYMENT = "payment"
    REFUND = "refund"
    TRANSFER = "transfer"
    ADJUSTMENT = "adjustment"


@dataclass(frozen=True, slots=True)
class SettlementItem:
    """One line of the gateway's settlement report, amounts in paise."""

    entity_id: str
    kind: str
    amount_paise: int
    # What the gateway kept, its GST included.
    fee_paise: int
    tax_paise: int
    credit_paise: int
    debit_paise: int
    currency: str
    settled: bool
    settlement_id: str | None
    # For a refund, the payment it gave back.
    payment_id: str | None


class IssueKind(StrEnum):
    """What reconciliation found that someone has to look at."""

    UNKNOWN_PAYMENT = "unknown_payment"
    UNKNOWN_REFUND = "unknown_refund"
    AMOUNT_MISMATCH = "amount_mismatch"
    NOT_CAPTURED_HERE = "not_captured_here"
    REFUND_NOT_PROCESSED_HERE = "refund_not_processed_here"
    UNEXPECTED_ITEM = "unexpected_item"
    NOT_SETTLED = "not_settled"
    STUCK_AUTHORIZED = "stuck_authorized"
    REFUND_STUCK = "refund_stuck"
    LINK_MISMATCH = "link_mismatch"


@dataclass(frozen=True, slots=True)
class Ours:
    """What we hold about an item's payment or refund."""

    amount_paise: int
    # Captured, for a payment; processed, for a refund.
    done: bool


@dataclass(frozen=True, slots=True)
class ItemReading:
    issue: IssueKind | None
    # What to post: the fee kept, what reached the bank, and a refund taken back.
    fee_paise: int = 0
    settled_paise: int = 0
    refund_paise: int = 0


def read_item(item: SettlementItem, ours: Ours | None) -> ItemReading:
    """What one line of the report comes to against what we hold."""
    if item.kind == ItemKind.PAYMENT:
        return _payment_line(item, ours)
    if item.kind == ItemKind.REFUND:
        return _refund_line(item, ours)
    # Transfers come with split settlement (Phase 9); adjustments need a person.
    return ItemReading(IssueKind.UNEXPECTED_ITEM)


def _payment_line(item: SettlementItem, ours: Ours | None) -> ItemReading:
    if ours is None:
        return ItemReading(IssueKind.UNKNOWN_PAYMENT)
    if item.amount_paise != ours.amount_paise:
        return ItemReading(IssueKind.AMOUNT_MISMATCH)
    if not ours.done:
        return ItemReading(IssueKind.NOT_CAPTURED_HERE)
    return ItemReading(
        None, fee_paise=item.fee_paise, settled_paise=item.credit_paise if item.settled else 0
    )


def _refund_line(item: SettlementItem, ours: Ours | None) -> ItemReading:
    if ours is None:
        return ItemReading(IssueKind.UNKNOWN_REFUND)
    if item.amount_paise != ours.amount_paise:
        return ItemReading(IssueKind.AMOUNT_MISMATCH)
    if not ours.done:
        return ItemReading(IssueKind.REFUND_NOT_PROCESSED_HERE)
    return ItemReading(None, refund_paise=item.debit_paise if item.settled else 0)


def is_stuck(made_at: datetime, now: datetime) -> bool:
    """Whether a checkout is due a question: old enough to have come back, young enough to
    still be paid."""
    return now - GIVE_UP_AFTER <= made_at <= now - STUCK_AFTER
