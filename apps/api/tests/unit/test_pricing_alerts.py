"""Pricing's integrity alerts (step 4.8, ADR 0043), without a database: when each is due, and
what makes it one alert."""

from datetime import date

import pytest

from app.modules.pricing.domain.alerts import (
    MAX_WEEKLY_ACTIVATIONS,
    MIN_COMPARABLES,
    MIN_WEEKLY_QUOTES,
    AlertKind,
    alert_key,
    below_market,
    churning,
    clamps_frequent,
    week_of,
)


@pytest.mark.parametrize(
    ("rent", "median", "comparables", "alert"),
    [
        # 25% below ₹10,000 is ₹7,500: only below that alerts.
        (749_900, 1_000_000, 3, True),
        (750_000, 1_000_000, 3, False),
        (1_000_000, 1_000_000, 3, False),
        # Too few to compare with, or none at all.
        (500_000, 1_000_000, MIN_COMPARABLES - 1, False),
        (500_000, None, 0, False),
    ],
)
def test_a_rent_is_below_the_market_only_past_a_quarter_below_its_median(
    rent: int, median: int | None, comparables: int, alert: bool
) -> None:
    assert below_market(rent, median, comparables) is alert


@pytest.mark.parametrize(
    ("quotes", "clamped", "alert"),
    [
        (10, 3, True),
        # Exactly 20% isn't more than 20%.
        (10, 2, False),
        (100, 21, True),
        (100, 20, False),
        # Too few quotes to say.
        (MIN_WEEKLY_QUOTES - 1, MIN_WEEKLY_QUOTES - 1, False),
    ],
)
def test_clamps_are_frequent_past_a_fifth_of_a_weeks_quotes(
    quotes: int, clamped: int, alert: bool
) -> None:
    assert clamps_frequent(quotes, clamped) is alert


def test_rules_churn_past_three_activations_a_week() -> None:
    assert [churning(count) for count in range(MAX_WEEKLY_ACTIVATIONS + 2)] == [
        False,
        False,
        False,
        False,
        True,
    ]


def test_a_week_starts_on_monday() -> None:
    # 14 July 2027 is a Wednesday.
    assert week_of(date(2027, 7, 14)) == date(2027, 7, 12)
    assert week_of(date(2027, 7, 12)) == date(2027, 7, 12)
    assert week_of(date(2027, 7, 18)) == date(2027, 7, 12)


def test_an_alerts_key_names_its_kind_and_what_its_about() -> None:
    assert alert_key(AlertKind.CLAMPS_FREQUENT, "pg-1", date(2027, 7, 12)) == (
        "clamps_frequent:pg-1:2027-07-12"
    )
    assert alert_key(AlertKind.RENT_BELOW_MARKET, "room-1", 700_000) != alert_key(
        AlertKind.RENT_BELOW_MARKET, "room-1", 650_000
    )
