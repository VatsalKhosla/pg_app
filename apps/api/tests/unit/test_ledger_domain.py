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
    gateway_fee,
    net,
    owner_invoiced,
    owner_paid,
    owner_refunded,
    refund_settled,
    settled,
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


def _balances(*postings: Posting) -> dict[Account, int]:
    """Debits less credits on each account, leaving out what's nothing."""
    found: dict[Account, int] = {}
    for posting in postings:
        for line in posting.lines:
            signed = line.amount_paise if line.direction is Direction.DEBIT else -line.amount_paise
            found[line.account] = found.get(line.account, 0) + signed
    return {account: balance for account, balance in found.items() if balance}


def test_an_owner_who_pays_the_balance_owes_nothing_and_the_gateway_holds_the_fee() -> None:
    """Step 6.5, the ₹10,000 example: the token pays ₹2,000 of the ₹3,540, the owner the rest."""
    books = _balances(
        token_received(rupees(2_000)),
        token_applied(rupees(2_000)),
        owner_invoiced(rupees(3_000), rupees(540)),
        owner_paid(rupees(1_540)),
    )

    assert books == {
        Account.GATEWAY_CLEARING: rupees(3_540),
        Account.PLACEMENT_FEE_REVENUE: -rupees(3_000),
        Account.GST_PAYABLE: -rupees(540),
    }


def test_a_token_above_the_fee_is_owed_to_the_owner() -> None:
    books = _balances(
        token_received(rupees(2_000)),
        token_applied(rupees(1_770), rupees(230)),
        owner_invoiced(rupees(1_500), rupees(270)),
    )

    assert books == {
        Account.GATEWAY_CLEARING: rupees(2_000),
        Account.OWNER_PAYABLE: -rupees(230),
        Account.PLACEMENT_FEE_REVENUE: -rupees(1_500),
        Account.GST_PAYABLE: -rupees(270),
    }


def test_an_owners_payment_given_back_is_owed_again() -> None:
    books = _balances(owner_paid(rupees(1_540)), owner_refunded(rupees(1_540)))

    assert books == {}


def test_the_settlement_report_empties_the_gateways_account_into_the_bank() -> None:
    """Step 6.6: a token in, then refunded, then settled: the bank is short only the fee."""
    books = _balances(
        token_received(rupees(2_000)),
        token_refunded(rupees(2_000)),
        gateway_fee(rupees(47)),
        settled(rupees(1_953)),
        refund_settled(rupees(2_000)),
    )

    assert books == {Account.PAYMENT_FEES: rupees(47), Account.BANK: -rupees(47)}
