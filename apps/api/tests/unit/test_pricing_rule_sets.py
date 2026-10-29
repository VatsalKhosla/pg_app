"""Rule sets' rules (step 4.3, ADR 0038), without a database: the moves a set may make, the
rules' JSON, and what stops a set going into force, said so ops can act on it."""

from datetime import date

import pytest
from hypothesis import given

from app.core.money import Paise, rupees
from app.modules.pricing.domain.engine import (
    EarlyBirdRule,
    MonthDay,
    OverrideRule,
    PricingRule,
    RuleKind,
    RuleParams,
    SeasonRule,
)
from app.modules.pricing.domain.policies import BandSource, RentBand
from app.modules.pricing.domain.rule_sets import (
    MAX_RULES,
    CategoryBounds,
    RuleSetStatus,
    can_move,
    params_from_json,
    params_to_json,
    rule_set_problems,
)
from tests.unit.test_pricing_engine import RULE_PARAMS

DOUBLE = CategoryBounds(
    category_id=1,
    name="Double sharing",
    base_rent_paise=rupees(10_000),
    owner_min_paise=None,
    owner_max_paise=None,
    band=None,
)
SINGLE = CategoryBounds(
    category_id=2,
    name="Single",
    base_rent_paise=rupees(14_000),
    owner_min_paise=None,
    owner_max_paise=None,
    band=None,
)


def season(label: str, start: str, end: str, **changes: object) -> PricingRule:
    rule = PricingRule(label, SeasonRule(MonthDay.parse(start), MonthDay.parse(end), 1_000))
    return PricingRule(
        rule.label,
        rule.params,
        room_category_ids=changes.get("categories"),  # type: ignore[arg-type]
        enabled=bool(changes.get("enabled", True)),
    )


@pytest.mark.parametrize("current", list(RuleSetStatus))
@pytest.mark.parametrize("target", list(RuleSetStatus))
def test_a_set_moves_only_forward(current: RuleSetStatus, target: RuleSetStatus) -> None:
    allowed = {
        (RuleSetStatus.DRAFT, RuleSetStatus.ACTIVE),
        (RuleSetStatus.ACTIVE, RuleSetStatus.ARCHIVED),
    }
    assert can_move(current, target) is ((current, target) in allowed)


@given(RULE_PARAMS)
def test_every_rule_comes_back_from_its_json_as_it_went_in(params: RuleParams) -> None:
    kind = PricingRule("A rule", params).kind

    assert params_from_json(kind, params_to_json(params)) == params


@pytest.mark.parametrize(
    ("kind", "data"),
    [
        (RuleKind.SEASON, {"start": "06-01", "end": "08-31"}),
        (RuleKind.SEASON, {"start": 601, "end": "08-31", "bps": 100}),
        (RuleKind.EARLY_BIRD, {"min_days_before": True, "bps": -100}),
        (RuleKind.OCCUPANCY, {"tiers": "many"}),
    ],
)
def test_stored_json_that_isnt_a_rule_is_refused(kind: RuleKind, data: dict[str, object]) -> None:
    with pytest.raises(ValueError, match=r"must be"):
        params_from_json(kind, data)


def test_a_set_without_problems_may_go_into_force() -> None:
    rules = [season("Summer", "05-01", "06-30"), season("Monsoon", "07-01", "09-15")]

    assert rule_set_problems(rules, [DOUBLE, SINGLE]) == []


def test_seasons_that_overlap_for_a_category_are_named() -> None:
    rules = [season("Peak", "06-01", "08-31"), season("Admissions", "08-15", "09-15")]

    assert rule_set_problems(rules, [DOUBLE]) == [
        "the seasons 'Peak' and 'Admissions' both cover 08-15 for Double sharing:"
        " seasons may not overlap"
    ]


def test_seasons_over_the_new_year_overlap_too() -> None:
    rules = [season("Winter", "12-15", "01-15"), season("New year", "01-01", "01-07")]

    assert "both cover 01-01" in rule_set_problems(rules, [DOUBLE])[0]


def test_seasons_for_different_categories_or_switched_off_dont_clash() -> None:
    rules = [
        season("Peak", "06-01", "08-31", categories=frozenset({1})),
        season("Single peak", "06-01", "08-31", categories=frozenset({2})),
        season("Old peak", "06-01", "08-31", categories=frozenset({1}), enabled=False),
    ]

    assert rule_set_problems(rules, [DOUBLE, SINGLE]) == []


def test_overrides_that_overlap_are_named() -> None:
    rules = [
        PricingRule("Diwali", OverrideRule(date(2027, 10, 25), date(2027, 11, 5), rupees(9_000))),
        PricingRule("Fest", OverrideRule(date(2027, 11, 1), date(2027, 11, 10), rupees(9_500))),
    ]

    assert rule_set_problems(rules, [DOUBLE]) == [
        "the overrides 'Diwali' and 'Fest' both cover 2027-11-01 for Double sharing: one rent a day"
    ]


def test_an_override_outside_the_band_and_bounds_that_leave_no_rent_are_named() -> None:
    band = RentBand(rupees(8_000), rupees(12_000), BandSource.INTERNAL, "")
    banded = CategoryBounds(1, "Double sharing", rupees(10_000), rupees(12_500), None, band)
    rules = [
        PricingRule("Fest", OverrideRule(date(2027, 11, 1), date(2027, 11, 3), rupees(13_000)))
    ]

    assert rule_set_problems(rules, [banded]) == [
        "Double sharing has no rent it may charge: the lowest allowed, ₹12,500.00, is above the"
        " highest, ₹12,000.00",
        "the override 'Fest' sets ₹13,000.00 for Double sharing, outside its locality's band of"
        " ₹8,000.00 to ₹12,000.00",
    ]


def test_rules_for_room_categories_the_pg_doesnt_have_and_too_many_rules_are_named() -> None:
    elsewhere = PricingRule("Early", EarlyBirdRule(30, -500), room_category_ids=frozenset({99}))
    many = [PricingRule("Early", EarlyBirdRule(30, -500))] * (MAX_RULES + 1)

    assert rule_set_problems([elsewhere], [DOUBLE]) == [
        "'Early' is for a room category this PG doesn't have"
    ]
    assert f"a set holds {MAX_RULES} rules at most" in rule_set_problems(many, [DOUBLE])


def test_a_month_day_reads_both_ways() -> None:
    assert str(MonthDay.parse("02-29")) == "02-29"
    assert params_to_json(SeasonRule(MonthDay(2, 29), MonthDay(3, 1), -100)) == {
        "start": "02-29",
        "end": "03-01",
        "bps": -100,
    }
    assert params_to_json(OverrideRule(date(2027, 1, 1), date(2027, 1, 2), Paise(500_000))) == {
        "start": "2027-01-01",
        "end": "2027-01-02",
        "rent_paise": 500_000,
    }
