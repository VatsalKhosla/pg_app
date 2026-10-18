import re
from decimal import ROUND_HALF_UP, Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.money import apply_bps, divide_round_half_up, format_inr, round_to_step, rupees

AMOUNTS = st.integers(min_value=-(10**15), max_value=10**15)  # ±₹10 lakh crore
POSITIVE = st.integers(min_value=1, max_value=10**9)


def _decimal_half_up(numerator: int, denominator: int) -> int:
    quotient = Decimal(numerator) / Decimal(denominator)
    return int(quotient.quantize(Decimal(1), rounding=ROUND_HALF_UP))


@pytest.mark.parametrize(
    ("numerator", "denominator", "expected"),
    [(5, 2, 3), (7, 2, 4), (-5, 2, -3), (4, 3, 1), (5, 3, 2), (0, 7, 0), (10_001, 10_000, 1)],
)
def test_halves_round_away_from_zero(numerator: int, denominator: int, expected: int) -> None:
    assert divide_round_half_up(numerator, denominator) == expected


@given(AMOUNTS, POSITIVE)
def test_division_matches_decimal_round_half_up(numerator: int, denominator: int) -> None:
    assert divide_round_half_up(numerator, denominator) == _decimal_half_up(numerator, denominator)


@pytest.mark.parametrize("denominator", [0, -1])
def test_division_needs_a_positive_denominator(denominator: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        divide_round_half_up(1, denominator)


def test_the_placement_fee_example_from_the_product_context() -> None:
    rent = rupees(10_000)

    fee = apply_bps(rent, 3_000)  # 30% of the listed rent
    gst = apply_bps(fee, 1_800)  # 18% GST, exclusive mode

    assert (fee, gst, fee + gst) == (rupees(3_000), rupees(540), rupees(3_540))


@given(st.integers(min_value=0, max_value=10**12), st.integers(min_value=0, max_value=10_000))
def test_a_share_of_an_amount_never_exceeds_it_and_grows_with_the_rate(
    amount: int, bps: int
) -> None:
    share = apply_bps(amount, bps)

    assert 0 <= share <= amount
    assert apply_bps(amount, 0) == 0
    assert apply_bps(amount, 10_000) == amount
    assert share <= apply_bps(amount, min(bps + 1, 10_000))


@given(AMOUNTS, POSITIVE)
def test_rounding_to_a_step_gives_the_nearest_multiple(amount: int, step: int) -> None:
    rounded = round_to_step(amount, step)

    assert rounded % step == 0
    assert abs(rounded - amount) * 2 <= step


def test_rounding_to_fifty_rupees() -> None:
    step = rupees(50)

    assert round_to_step(rupees(10_324), step) == rupees(10_300)
    assert round_to_step(rupees(10_325), step) == rupees(10_350)  # the half goes up


@pytest.mark.parametrize(
    ("paise", "text"),
    [
        (0, "₹0.00"),
        (5, "₹0.05"),
        (100_000, "₹1,000.00"),
        (1_000_050, "₹10,000.50"),
        (10_000_000, "₹1,00,000.00"),
        (123_456_789, "₹12,34,567.89"),
        (1_000_000_000_00, "₹1,00,00,00,000.00"),
        (-354_000, "-₹3,540.00"),
    ],
)
def test_formats_rupees_with_indian_digit_grouping(paise: int, text: str) -> None:
    assert format_inr(paise) == text


@given(AMOUNTS)
def test_formatting_keeps_the_exact_amount(paise: int) -> None:
    text = format_inr(paise)

    assert re.fullmatch(r"-?₹\d{1,3}(,\d{2})*(,\d{3})?\.\d{2}|-?₹\d{1,3}\.\d{2}", text)
    digits = text.replace("₹", "").replace(",", "")
    assert Decimal(digits) * 100 == paise
