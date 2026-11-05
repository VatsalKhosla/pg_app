"""The books (ARCHITECTURE §9.4; step 6.4, ADR 0060). Pure.

Every money event is a posting of debits and credits that add up. A posting that doesn't balance
can't be made here, and the database refuses one as well, when its transaction commits.

The accounting treatment is for a CA to confirm (founders' guide, section 8). Changing how an event
posts means changing its function here, and nothing else.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable


class AccountType(StrEnum):
    ASSET = "asset"
    LIABILITY = "liability"
    REVENUE = "revenue"
    EXPENSE = "expense"


class Account(StrEnum):
    GATEWAY_CLEARING = "gateway_clearing"
    BANK = "bank"
    OWNER_RECEIVABLE = "owner_receivable"
    STUDENT_TOKENS_HELD = "student_tokens_held"
    OWNER_PAYABLE = "owner_payable"
    GST_PAYABLE = "gst_payable"
    PLACEMENT_FEE_REVENUE = "placement_fee_revenue"
    PAYMENT_FEES = "payment_fees"


# The chart of accounts, which a migration seeds and a test holds to this.
CHART: Final[dict[Account, tuple[AccountType, str]]] = {
    Account.GATEWAY_CLEARING: (AccountType.ASSET, "Gateway clearing"),
    Account.BANK: (AccountType.ASSET, "Bank"),
    Account.OWNER_RECEIVABLE: (AccountType.ASSET, "Owed by owners"),
    Account.STUDENT_TOKENS_HELD: (AccountType.LIABILITY, "Students' tokens held"),
    Account.OWNER_PAYABLE: (AccountType.LIABILITY, "Owed to owners"),
    Account.GST_PAYABLE: (AccountType.LIABILITY, "GST payable"),
    Account.PLACEMENT_FEE_REVENUE: (AccountType.REVENUE, "Placement fees"),
    Account.PAYMENT_FEES: (AccountType.EXPENSE, "Payment gateway fees"),
}


class Direction(StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"


class PostingKind(StrEnum):
    TOKEN_RECEIVED = "token_received"  # noqa: S105 - a kind of posting
    TOKEN_REFUNDED = "token_refunded"  # noqa: S105 - a kind of posting
    OWNER_INVOICED = "owner_invoiced"
    TOKEN_APPLIED = "token_applied"  # noqa: S105 - a kind of posting


class UnbalancedPostingError(ValueError):
    """A posting's debits and credits don't add up, or it holds an amount that makes no sense."""


@dataclass(frozen=True, slots=True)
class Line:
    account: Account
    direction: Direction
    amount_paise: int


@dataclass(frozen=True, slots=True)
class Posting:
    kind: PostingKind
    lines: tuple[Line, ...]

    def __post_init__(self) -> None:
        if not self.lines or any(line.amount_paise <= 0 for line in self.lines):
            msg = f"{self.kind} needs lines of more than nothing"
            raise UnbalancedPostingError(msg)
        difference = net(self.lines)
        if difference != 0:
            msg = f"{self.kind} is out by {difference} paise"
            raise UnbalancedPostingError(msg)


def net(lines: Iterable[Line]) -> int:
    """Debits less credits."""
    return sum(
        line.amount_paise if line.direction is Direction.DEBIT else -line.amount_paise
        for line in lines
    )


def _debit(account: Account, amount_paise: int) -> Line:
    return Line(account, Direction.DEBIT, amount_paise)


def _credit(account: Account, amount_paise: int) -> Line:
    return Line(account, Direction.CREDIT, amount_paise)


def token_received(amount_paise: int) -> Posting:
    """The gateway has a student's token, which we hold for them until it's earned or goes back."""
    return Posting(
        PostingKind.TOKEN_RECEIVED,
        (
            _debit(Account.GATEWAY_CLEARING, amount_paise),
            _credit(Account.STUDENT_TOKENS_HELD, amount_paise),
        ),
    )


def token_refunded(amount_paise: int) -> Posting:
    return Posting(
        PostingKind.TOKEN_REFUNDED,
        (
            _debit(Account.STUDENT_TOKENS_HELD, amount_paise),
            _credit(Account.GATEWAY_CLEARING, amount_paise),
        ),
    )


def owner_invoiced(fee_paise: int, gst_paise: int) -> Posting:
    """A tenant has moved in, so the owner owes the placement fee and its GST (rule 2)."""
    return Posting(
        PostingKind.OWNER_INVOICED,
        (
            _debit(Account.OWNER_RECEIVABLE, fee_paise + gst_paise),
            _credit(Account.PLACEMENT_FEE_REVENUE, fee_paise),
            *((_credit(Account.GST_PAYABLE, gst_paise),) if gst_paise > 0 else ()),
        ),
    )


def token_applied(amount_paise: int) -> Posting:
    """The token is earned: what we held for the student now pays part of what the owner owes."""
    return Posting(
        PostingKind.TOKEN_APPLIED,
        (
            _debit(Account.STUDENT_TOKENS_HELD, amount_paise),
            _credit(Account.OWNER_RECEIVABLE, amount_paise),
        ),
    )
