"""The books (step 6.4, ADR 0060): every posting balances, and a whole booking's life adds up."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.money import rupees
from app.modules.ledger.domain.ledger import (
    CHART,
    Account,
    AccountType,
    Direction,
    Line,
    Posting,
    PostingKind,
    UnbalancedPostingError,
    net,
    owner_invoiced,
    token_applied,
    token_received,
    token_refunded,
)

A = Account
D = Direction
AMOUNT = st.integers(min_value=1, max_value=10_000_000)


def _totals(postings: list[Posting]) -> dict[Account, int]:
    """Debits less credits on each account."""
    found: dict[Account, int] = {}
    for posting in postings:
        for line in posting.lines:
            signed = line.amount_paise if line.direction is D.DEBIT else -line.amount_paise
            found[line.account] = found.get(line.account, 0) + signed
    return {account: total for account, total in found.items() if total != 0}


def test_the_chart_has_an_entry_for_every_account_of_the_right_kind() -> None:
    assert set(CHART) == set(Account)
    assert CHART[A.GATEWAY_CLEARING][0] is AccountType.ASSET
    assert CHART[A.STUDENT_TOKENS_HELD][0] is AccountType.LIABILITY
    assert CHART[A.PLACEMENT_FEE_REVENUE][0] is AccountType.REVENUE
    assert CHART[A.PAYMENT_FEES][0] is AccountType.EXPENSE


def test_the_worked_example_in_the_architecture_posts_as_it_says() -> None:
    """The ₹10,000 room of §9.4: a fee of ₹3,000, GST of ₹540 and a token of ₹2,000."""
    token, fee, gst = rupees(2_000), rupees(3_000), rupees(540)

    assert token_received(token).lines == (
        Line(A.GATEWAY_CLEARING, D.DEBIT, token),
        Line(A.STUDENT_TOKENS_HELD, D.CREDIT, token),
    )
    assert token_refunded(token).lines == (
        Line(A.STUDENT_TOKENS_HELD, D.DEBIT, token),
        Line(A.GATEWAY_CLEARING, D.CREDIT, token),
    )
    assert owner_invoiced(fee, gst).lines == (
        Line(A.OWNER_RECEIVABLE, D.DEBIT, rupees(3_540)),
        Line(A.PLACEMENT_FEE_REVENUE, D.CREDIT, fee),
        Line(A.GST_PAYABLE, D.CREDIT, gst),
    )
    assert token_applied(token).lines == (
        Line(A.STUDENT_TOKENS_HELD, D.DEBIT, token),
        Line(A.OWNER_RECEIVABLE, D.CREDIT, token),
    )
    assert _totals([token_received(token), owner_invoiced(fee, gst), token_applied(token)]) == {
        A.GATEWAY_CLEARING: token,
        A.OWNER_RECEIVABLE: rupees(1_540),
        A.PLACEMENT_FEE_REVENUE: -fee,
        A.GST_PAYABLE: -gst,
    }


def test_a_fee_with_no_gst_has_no_gst_line() -> None:
    assert owner_invoiced(100, 0).lines == (
        Line(A.OWNER_RECEIVABLE, D.DEBIT, 100),
        Line(A.PLACEMENT_FEE_REVENUE, D.CREDIT, 100),
    )


def test_a_token_that_goes_back_leaves_nothing_on_the_books() -> None:
    assert _totals([token_received(200_000), token_refunded(200_000)]) == {}


@pytest.mark.parametrize(
    "lines",
    [
        (),
        (Line(A.BANK, D.DEBIT, 100),),
        (Line(A.BANK, D.DEBIT, 100), Line(A.GATEWAY_CLEARING, D.CREDIT, 99)),
        (Line(A.BANK, D.DEBIT, 0), Line(A.GATEWAY_CLEARING, D.CREDIT, 0)),
        (Line(A.BANK, D.DEBIT, -1), Line(A.GATEWAY_CLEARING, D.CREDIT, -1)),
    ],
)
def test_a_posting_that_doesnt_balance_cant_be_made(lines: tuple[Line, ...]) -> None:
    with pytest.raises(UnbalancedPostingError):
        Posting(PostingKind.TOKEN_RECEIVED, lines)


@pytest.mark.parametrize("amount", [0, -1])
def test_nothing_or_less_cant_be_posted(amount: int) -> None:
    with pytest.raises(UnbalancedPostingError):
        token_received(amount)


@given(AMOUNT, AMOUNT, st.integers(min_value=0, max_value=10_000_000))
def test_every_posting_balances_whatever_the_amounts(token: int, fee: int, gst: int) -> None:
    for posting in (
        token_received(token),
        token_refunded(token),
        token_applied(token),
        owner_invoiced(fee, gst),
    ):
        assert net(posting.lines) == 0


@given(
    st.lists(st.sampled_from(["received", "refunded", "applied", "invoiced"]), max_size=30),
    AMOUNT,
    AMOUNT,
    st.integers(min_value=0, max_value=10_000_000),
)
def test_the_books_add_up_after_any_events_in_any_order(
    events: list[str], token: int, fee: int, gst: int
) -> None:
    made = {
        "received": token_received(token),
        "refunded": token_refunded(token),
        "applied": token_applied(token),
        "invoiced": owner_invoiced(fee, gst),
    }
    postings = [made[event] for event in events]

    assert sum(_totals(postings).values()) == 0
