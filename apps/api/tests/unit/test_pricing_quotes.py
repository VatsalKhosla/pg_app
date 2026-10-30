"""Quotes' rules (step 4.4, ADR 0039), without a database: what can be quoted, the one-line
explanation, and the inputs' digest."""

import dataclasses
from datetime import date, timedelta

import pytest

from app.core.money import Paise, format_rupees, rupees
from app.modules.pricing.domain.engine import OverrideRule, PricingRule, quote
from app.modules.pricing.domain.quotes import (
    MAX_STAY_MONTHS,
    PREVIEW_DAYS,
    bookable_from,
    bps_text,
    explanation,
    inputs_digest,
    median_rent,
    preview_problems,
    quote_problems,
)
from tests.unit.test_pricing_engine import BOOKING, EARLY, LONG_STAY, PEAK, TODAY, context

MINUS = chr(0x2212)
VERSIONS = {"rule_set": 4, "fee_policy": 1, "booking_policy": 1, "pricing_caps": 1}


def test_the_worked_example_explains_itself() -> None:
    result = quote(context(rules=(PEAK, EARLY, LONG_STAY)))

    assert explanation(result) == (
        f"Base ₹10,000 · Peak season +15% · Early-bird {MINUS}5% · Long stay {MINUS}7%"
        " = ₹10,300/month, fixed for your stay"
    )


def test_an_override_says_its_rent() -> None:
    fixed = PricingRule(
        "Festival rate", OverrideRule(date(2027, 6, 15), date(2027, 7, 15), rupees(9_500))
    )

    assert explanation(quote(context(rules=(fixed,)))) == (
        "Base ₹10,000 · Festival rate ₹9,500 = ₹9,500/month, fixed for your stay"
    )


@pytest.mark.parametrize(
    ("bps", "text"),
    [(1_500, "+15%"), (-500, f"{MINUS}5%"), (250, "+2.5%"), (-1, f"{MINUS}0.01%"), (0, "+0%")],
)
def test_a_rules_move_reads_as_a_percentage(bps: int, text: str) -> None:
    assert bps_text(bps) == text


def test_rupees_read_without_paise_unless_there_are_some() -> None:
    assert (format_rupees(rupees(10_300)), format_rupees(Paise(1_030_050))) == (
        "₹10,300",
        "₹10,300.50",
    )


def test_a_move_in_from_today_to_the_booking_horizon_can_be_quoted() -> None:
    horizon = TODAY + timedelta(days=BOOKING.max_advance_days)

    assert quote_problems(move_in=TODAY, stay_months=11, today=TODAY, booking=BOOKING) == []
    assert quote_problems(move_in=horizon, stay_months=1, today=TODAY, booking=BOOKING) == []
    assert quote_problems(
        move_in=TODAY - timedelta(days=1), stay_months=0, today=TODAY, booking=BOOKING
    ) == ["the move-in date has passed", f"a stay is from 1 to {MAX_STAY_MONTHS} months"]
    assert quote_problems(
        move_in=horizon + timedelta(days=1), stay_months=11, today=TODAY, booking=BOOKING
    ) == ["a move-in can be booked at most 120 days ahead"]


def test_the_inputs_digest_is_the_same_for_the_same_inputs_and_changes_with_any() -> None:
    ctx = context(rules=(PEAK, EARLY))
    digest = inputs_digest(ctx, versions=VERSIONS)

    assert digest == inputs_digest(context(rules=(PEAK, EARLY)), versions=dict(VERSIONS))
    assert len(digest) == 64
    others = [
        inputs_digest(dataclasses.replace(ctx, occupancy_bps=5_001), versions=VERSIONS),
        inputs_digest(dataclasses.replace(ctx, rules=(EARLY, PEAK)), versions=VERSIONS),
        inputs_digest(dataclasses.replace(ctx, today=TODAY + timedelta(days=1)), versions=VERSIONS),
        inputs_digest(ctx, versions=VERSIONS | {"rule_set": 5}),
    ]
    assert digest not in others
    assert len(set(others)) == len(others)


def test_the_editor_prices_from_today_to_a_year_ahead() -> None:
    year = TODAY + timedelta(days=PREVIEW_DAYS)

    assert preview_problems(move_in=TODAY, stay_months=36, today=TODAY) == []
    assert preview_problems(move_in=year, stay_months=1, today=TODAY) == []
    assert preview_problems(move_in=TODAY - timedelta(days=1), stay_months=37, today=TODAY) == [
        "the move-in date has passed",
        f"a stay is from 1 to {MAX_STAY_MONTHS} months",
    ]
    assert preview_problems(move_in=year + timedelta(days=1), stay_months=11, today=TODAY) == [
        "the editor prices move-ins up to a year ahead"
    ]


def test_a_move_in_beyond_the_horizon_says_when_students_can_quote_it() -> None:
    horizon = TODAY + timedelta(days=BOOKING.max_advance_days)

    assert bookable_from(horizon, today=TODAY, booking=BOOKING) is None
    assert bookable_from(TODAY, today=TODAY, booking=BOOKING) is None
    assert bookable_from(horizon + timedelta(days=9), today=TODAY, booking=BOOKING) == (
        TODAY + timedelta(days=9)
    )


@pytest.mark.parametrize(
    ("rents", "middle"),
    [
        ([], None),
        ([900_000], 900_000),
        ([1_250_000, 800_000, 900_000], 900_000),
        ([800_000, 1_250_000, 900_000, 1_000_000], 950_000),
        # The two middle ones' mean, rounded half-up to the paisa.
        ([100, 201], 151),
    ],
)
def test_the_market_median_is_the_middle_rent(rents: list[int], middle: int | None) -> None:
    assert median_rent(rents) == middle
