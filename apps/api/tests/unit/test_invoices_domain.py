"""An owner's invoice: what it comes to, and its number (step 6.5, ADR 0061). Done when the ₹10,000
example produces an invoice of ₹3,540 with ₹2,000 applied and ₹1,540 due."""

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.invoices.domain.invoices import (
    MAX_NUMBER_LENGTH,
    InvoiceStatus,
    financial_year,
    invoice_amounts,
    invoice_number,
    percent,
    status_on_issue,
)


def _seen(total: int, gst: int, token: int) -> tuple[int, ...]:
    amounts = invoice_amounts(total_paise=total, gst_paise=gst, token_paise=token)
    return (
        amounts.fee_paise,
        amounts.gst_paise,
        amounts.total_paise,
        amounts.token_applied_paise,
        amounts.token_over_paise,
        amounts.balance_due_paise,
    )


def test_the_ten_thousand_rupee_example_leaves_1540_to_pay() -> None:
    # 30% of ₹10,000 is ₹3,000, with 18% GST added: ₹3,540, of which the token paid ₹2,000.
    assert _seen(354_000, 54_000, 200_000) == (300_000, 54_000, 354_000, 200_000, 0, 154_000)
    amounts = invoice_amounts(total_paise=354_000, gst_paise=54_000, token_paise=200_000)
    assert status_on_issue(amounts) is InvoiceStatus.ISSUED


def test_with_the_gst_included_the_fee_is_what_the_gst_leaves() -> None:
    # gst_mode inclusive: the ₹3,000 holds its GST, ₹457.63 of it.
    assert _seen(300_000, 45_763, 200_000) == (254_237, 45_763, 300_000, 200_000, 0, 100_000)


def test_a_token_above_the_fee_pays_all_of_it_and_the_rest_is_the_owners() -> None:
    amounts = invoice_amounts(total_paise=177_000, gst_paise=27_000, token_paise=200_000)
    assert _seen(177_000, 27_000, 200_000) == (150_000, 27_000, 177_000, 177_000, 23_000, 0)
    assert status_on_issue(amounts) is InvoiceStatus.PAID


@given(
    total=st.integers(min_value=0, max_value=10**9),
    gst=st.integers(min_value=0, max_value=10**9),
    token=st.integers(min_value=0, max_value=10**9),
)
def test_an_invoice_always_adds_up(total: int, gst: int, token: int) -> None:
    gst %= total + 1
    amounts = invoice_amounts(total_paise=total, gst_paise=gst, token_paise=token)
    assert amounts.fee_paise + amounts.gst_paise == amounts.total_paise
    assert amounts.token_applied_paise + amounts.balance_due_paise == amounts.total_paise
    assert amounts.token_applied_paise + amounts.token_over_paise == token
    assert amounts.token_over_paise == 0 or amounts.balance_due_paise == 0
    assert min(_seen(total, gst, token)) >= 0


@pytest.mark.parametrize(
    ("total", "gst", "token"), [(-1, 0, 0), (100, 101, 0), (100, 0, -1), (100, -1, 0)]
)
def test_an_invoice_that_makes_no_sense_is_refused(total: int, gst: int, token: int) -> None:
    with pytest.raises(ValueError, match="nothing negative"):
        invoice_amounts(total_paise=total, gst_paise=gst, token_paise=token)


@pytest.mark.parametrize(
    ("day", "year"),
    [
        (date(2027, 3, 31), "2026-27"),
        (date(2027, 4, 1), "2027-28"),
        (date(2026, 11, 6), "2026-27"),
        (date(2099, 12, 31), "2099-00"),
        (date(2100, 3, 31), "2099-00"),
    ],
)
def test_financial_years_run_from_april_to_march(day: date, year: str) -> None:
    assert financial_year(day) == year


@given(st.dates(min_value=date(2000, 1, 1), max_value=date(9998, 12, 31)))
def test_every_day_falls_in_the_year_from_the_april_before_it(day: date) -> None:
    year = financial_year(day)
    first = int(year[:4])
    assert date(first, 4, 1) <= day < date(first + 1, 4, 1)
    assert year[5:] == f"{(first + 1) % 100:02d}"


def test_numbers_are_as_gst_allows() -> None:
    assert invoice_number("2027-28", 123) == "FY2027-28/000123"
    assert len(invoice_number("2027-28", 999_999)) == MAX_NUMBER_LENGTH
    for serial in (0, 1_000_000):
        with pytest.raises(ValueError, match="no invoice number"):
            invoice_number("2027-28", serial)


@pytest.mark.parametrize(
    ("bps", "written"), [(3_000, "30%"), (1_800, "18%"), (1_250, "12.5%"), (1_205, "12.05%")]
)
def test_rates_read_as_people_write_them(bps: int, written: str) -> None:
    assert percent(bps) == written
