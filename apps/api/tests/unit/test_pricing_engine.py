"""The pricing engine (step 4.2, ADR 0037; ARCHITECTURE §8): the worked example and other cases
by hand, then every invariant of §8.8 as a property, on 200 generated cases each locally and
10,000 in CI (tests/conftest.py)."""

import dataclasses
from datetime import date, timedelta

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from app.core.money import BasisPoints, Paise, rupees
from app.modules.pricing.domain.engine import (
    ENGINE_VERSION,
    Clamp,
    ClampKind,
    EarlyBirdRule,
    ImpossibleBoundsError,
    LastMinuteRule,
    LengthOfStayRule,
    MonthDay,
    OccupancyRule,
    OccupancyTier,
    OverrideRule,
    PricingContext,
    PricingRule,
    Quote,
    RuleKind,
    SeasonRule,
    StayTier,
    bounds,
    quote,
)
from app.modules.pricing.domain.policies import (
    BandSource,
    BookingPolicy,
    FeeBasis,
    FeePolicy,
    GstMode,
    LateCancelPolicy,
    PricingCaps,
    RentBand,
)

CATEGORY = 7
TODAY = date(2027, 5, 1)
FEE = FeePolicy(
    rate_bps=BasisPoints(3_000),
    basis=FeeBasis.LISTED_RENT,
    gst_rate_bps=BasisPoints(1_800),
    gst_mode=GstMode.EXCLUSIVE,
)
BOOKING = BookingPolicy(
    token_paise=rupees(2_000),
    hold_minutes=15,
    free_cancel_days=7,
    check_window_hours=24,
    confirm_deadline_hours=12,
    no_show_days=3,
    late_cancel_policy=LateCancelPolicy.REFUND_FULL,
    max_active_holds_per_user=1,
    max_advance_days=120,
)
CAPS = PricingCaps(
    max_premium_bps=BasisPoints(4_000),
    max_discount_bps=BasisPoints(3_000),
    rounding_step_paise=rupees(50),
)
PEAK = PricingRule("Peak season", SeasonRule(MonthDay(6, 1), MonthDay(8, 31), 1_500))
EARLY = PricingRule("Early-bird", EarlyBirdRule(min_days_before=30, bps=-500))
LONG_STAY = PricingRule("Long stay", LengthOfStayRule((StayTier(6, -300), StayTier(11, -700))))


def context(**changes: object) -> PricingContext:
    base = PricingContext(
        room_category_id=CATEGORY,
        base_rent_paise=rupees(10_000),
        owner_min_paise=None,
        owner_max_paise=None,
        move_in=date(2027, 7, 1),
        stay_months=11,
        today=TODAY,
        occupancy_bps=5_000,
        rules=(),
        band=None,
        fee_policy=FEE,
        booking_policy=BOOKING,
        caps=CAPS,
    )
    return dataclasses.replace(base, **changes)  # type: ignore[arg-type]


def test_the_worked_example() -> None:
    # ARCHITECTURE §8.3: ₹10,000 in July, a 15% season, 5% off early, 7% off an 11-month stay.
    result = quote(context(rules=(PEAK, EARLY, LONG_STAY)))

    assert result == Quote(
        base_rent_paise=rupees(10_000),
        monthly_rent_paise=rupees(10_300),
        adjustments=result.adjustments,
        clamps=(),
        premium_bps=1_500,
        discount_bps=1_200,
        fee_paise=rupees(3_000),
        gst_paise=rupees(540),
        owner_fee_total_paise=rupees(3_540),
        token_paise=rupees(2_000),
        due_at_move_in_paise=rupees(8_300),
        engine_version=ENGINE_VERSION,
    )
    assert [(item.kind, item.label, item.bps) for item in result.adjustments] == [
        (RuleKind.SEASON, "Peak season", 1_500),
        (RuleKind.EARLY_BIRD, "Early-bird", -500),
        (RuleKind.LENGTH_OF_STAY, "Long stay", -700),
    ]


def test_no_rules_charge_the_listed_rent() -> None:
    result = quote(context())

    assert result.monthly_rent_paise == rupees(10_000)
    assert result.adjustments == ()


@pytest.mark.parametrize(
    ("move_in", "matches"),
    [
        (date(2027, 12, 20), True),
        (date(2028, 1, 10), True),
        (date(2028, 1, 15), True),
        (date(2028, 1, 16), False),
        (date(2027, 12, 14), False),
    ],
)
def test_a_season_may_wrap_the_year(move_in: date, matches: bool) -> None:
    winter = PricingRule("Winter", SeasonRule(MonthDay(12, 15), MonthDay(1, 15), -1_000))

    result = quote(context(rules=(winter,), move_in=move_in))

    assert (result.monthly_rent_paise == rupees(9_000)) is matches


def test_a_months_day_is_checked_against_a_leap_year() -> None:
    assert str(MonthDay.parse("02-29")) == "02-29"
    for text in ("02-30", "13-01", "7-15", "07/15"):
        with pytest.raises(ValueError, match=r"."):
            MonthDay.parse(text)


def test_caps_hold_premiums_and_discounts_back() -> None:
    surge = PricingRule("Full", OccupancyRule((OccupancyTier(5_000, 5_000),)))
    deep = PricingRule(
        "Quiet", LastMinuteRule(max_days_before=90, max_occupancy_bps=9_000, bps=-4_000)
    )

    up = quote(context(rules=(surge,)))
    down = quote(context(rules=(deep,)))

    assert (up.premium_bps, up.monthly_rent_paise) == (4_000, rupees(14_000))
    assert up.clamps == (Clamp(ClampKind.PREMIUM_CAP, 5_000, 4_000),)
    assert (down.discount_bps, down.monthly_rent_paise) == (3_000, rupees(7_000))
    assert down.clamps == (Clamp(ClampKind.DISCOUNT_CAP, 4_000, 3_000),)


def test_the_owners_bounds_and_the_band_hold_the_price_and_say_which() -> None:
    band = RentBand(rupees(9_500), rupees(12_000), BandSource.INTERNAL, "")
    cheap = PricingRule(
        "Quiet", LastMinuteRule(max_days_before=90, max_occupancy_bps=9_000, bps=-2_000)
    )
    dear = PricingRule("Full", OccupancyRule((OccupancyTier(1_000, 3_000),)))

    floor = quote(context(rules=(cheap,), owner_min_paise=rupees(9_000), band=band))
    ceiling = quote(context(rules=(dear,), owner_max_paise=rupees(15_000), band=band))
    owners = quote(context(rules=(cheap,), owner_min_paise=rupees(9_800), band=band))

    assert floor.monthly_rent_paise == rupees(9_500)
    assert floor.clamps == (Clamp(ClampKind.BAND_MIN, rupees(8_000), rupees(9_500)),)
    assert ceiling.monthly_rent_paise == rupees(12_000)
    assert ceiling.clamps == (Clamp(ClampKind.BAND_MAX, rupees(13_000), rupees(12_000)),)
    assert owners.clamps == (Clamp(ClampKind.OWNER_MIN, rupees(8_000), rupees(9_800)),)


def test_bounds_without_a_step_between_them_keep_the_price_inside() -> None:
    # No multiple of ₹50 lies from ₹10,010 to ₹10,040.
    result = quote(context(owner_min_paise=rupees(10_010), owner_max_paise=rupees(10_040)))

    assert result.monthly_rent_paise == rupees(10_010)


def test_bounds_that_leave_no_rent_are_refused() -> None:
    band = RentBand(rupees(8_000), rupees(9_000), BandSource.INTERNAL, "")

    with pytest.raises(ImpossibleBoundsError) as refused:
        quote(context(owner_min_paise=rupees(9_500), band=band))

    assert (refused.value.low, refused.value.high) == (rupees(9_500), rupees(9_000))


def test_an_override_sets_the_rent_and_the_other_rules_dont_apply() -> None:
    fixed = PricingRule(
        "Festival rate", OverrideRule(date(2027, 6, 15), date(2027, 7, 15), rupees(9_975))
    )

    result = quote(context(rules=(PEAK, fixed, EARLY)))

    assert [item.kind for item in result.adjustments] == [RuleKind.OVERRIDE]
    assert result.adjustments[0].rent_paise == rupees(9_975)
    # Still rounded to the step: ₹9,975 is halfway, so up.
    assert result.monthly_rent_paise == rupees(10_000)
    assert (result.premium_bps, result.discount_bps) == (0, 0)


def test_rules_for_other_categories_or_switched_off_dont_apply() -> None:
    elsewhere = dataclasses.replace(PEAK, room_category_ids=frozenset({CATEGORY + 1}))
    here = dataclasses.replace(EARLY, room_category_ids=frozenset({CATEGORY}))
    off = dataclasses.replace(LONG_STAY, enabled=False)

    result = quote(context(rules=(elsewhere, here, off)))

    assert [item.label for item in result.adjustments] == ["Early-bird"]


def test_the_fee_includes_gst_when_the_policy_says_so() -> None:
    inclusive = dataclasses.replace(FEE, gst_mode=GstMode.INCLUSIVE)

    result = quote(context(fee_policy=inclusive))

    # ₹3,000 with 18% GST inside: ₹2,542.37 net, ₹457.63 GST.
    assert (result.fee_paise, result.gst_paise, result.owner_fee_total_paise) == (
        rupees(3_000),
        Paise(45_763),
        rupees(3_000),
    )


def test_the_token_is_never_more_than_the_rent_and_a_rent_never_zero() -> None:
    small = quote(context(base_rent_paise=rupees(1_500)))
    tiny = quote(
        context(
            base_rent_paise=Paise(1), caps=dataclasses.replace(CAPS, rounding_step_paise=Paise(100))
        )
    )

    assert (small.token_paise, small.due_at_move_in_paise) == (rupees(1_500), Paise(0))
    assert tiny.monthly_rent_paise == Paise(100)


def test_last_minute_needs_both_the_days_and_empty_beds() -> None:
    rule = PricingRule(
        "Last minute", LastMinuteRule(max_days_before=10, max_occupancy_bps=6_000, bps=-1_000)
    )
    soon = TODAY + timedelta(days=5)

    assert quote(context(rules=(rule,), move_in=soon, occupancy_bps=6_000)).discount_bps == 1_000
    assert quote(context(rules=(rule,), move_in=soon, occupancy_bps=6_001)).discount_bps == 0
    assert quote(context(rules=(rule,), move_in=soon + timedelta(days=6))).discount_bps == 0


def _case(case_id: str, make: object, message: str) -> object:
    return pytest.param(make, message, id=case_id)


@pytest.mark.parametrize(
    ("make", "message"),
    [
        _case("still-season", lambda: SeasonRule(MonthDay(6, 1), MonthDay(8, 31), 0), "up or down"),
        _case("no-occupancy-tier", lambda: OccupancyRule(()), "needs a tier"),
        _case(
            "repeated-occupancy-tier",
            lambda: OccupancyRule((OccupancyTier(5_000, 100), OccupancyTier(5_000, 200))),
            "tiers go up",
        ),
        _case("empty-occupancy-tier", lambda: OccupancyRule((OccupancyTier(0, 100),)), "above 0%"),
        _case(
            "occupancy-discount",
            lambda: OccupancyRule((OccupancyTier(5_000, -100),)),
            "only adds",
        ),
        _case("same-day-early-bird", lambda: EarlyBirdRule(0, -100), "a day or more"),
        _case("early-bird-premium", lambda: EarlyBirdRule(30, 100), "only takes a discount"),
        _case("days-after-move-in", lambda: LastMinuteRule(-1, 5_000, -100), "counts days"),
        _case("full-last-minute", lambda: LastMinuteRule(5, 10_000, -100), "still empty"),
        _case(
            "last-minute-premium", lambda: LastMinuteRule(5, 5_000, 100), "only takes a discount"
        ),
        _case("no-stay-tier", lambda: LengthOfStayRule(()), "needs a tier"),
        _case(
            "stay-tiers-down",
            lambda: LengthOfStayRule((StayTier(6, -100), StayTier(3, -200))),
            "tiers go up",
        ),
        _case("one-month-tier", lambda: LengthOfStayRule((StayTier(1, -100),)), "above a month"),
        _case(
            "stay-premium", lambda: LengthOfStayRule((StayTier(6, 100),)), "only takes a discount"
        ),
        _case(
            "backwards-override",
            lambda: OverrideRule(date(2027, 7, 2), date(2027, 7, 1), rupees(9_000)),
            "ends on or after",
        ),
        _case(
            "free-override",
            lambda: OverrideRule(date(2027, 7, 1), date(2027, 7, 1), Paise(0)),
            "above zero",
        ),
        _case("blank-label", lambda: PricingRule(" ", EarlyBirdRule(30, -100)), "label"),
        _case("free-rent", lambda: context(base_rent_paise=Paise(0)), "above zero"),
        _case("no-months", lambda: context(stay_months=0), "a month or more"),
        _case("past-move-in", lambda: context(move_in=TODAY - timedelta(days=1)), "in the past"),
        _case("overfull", lambda: context(occupancy_bps=10_001), "from 0 to 100%"),
    ],
)
def test_rules_and_contexts_that_cant_be_say_why(make: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        make()  # type: ignore[operator]


# Properties (§8.8) ---------------------------------------------------------------------------

BPS = st.integers(min_value=1, max_value=5_000)
DAYS = st.dates(min_value=date(2026, 1, 1), max_value=date(2030, 12, 31))
MONTH_DAYS = st.builds(
    MonthDay.of, st.dates(min_value=date(2000, 1, 1), max_value=date(2000, 12, 31))
)


@st.composite
def season_rules(draw: st.DrawFn) -> SeasonRule:
    return SeasonRule(
        draw(MONTH_DAYS), draw(MONTH_DAYS), draw(BPS) * draw(st.sampled_from((1, -1)))
    )


@st.composite
def occupancy_rules(draw: st.DrawFn) -> OccupancyRule:
    levels = sorted(draw(st.sets(st.integers(1, 10_000), min_size=1, max_size=3)))
    return OccupancyRule(tuple(OccupancyTier(level, draw(BPS)) for level in levels))


@st.composite
def length_of_stay_rules(draw: st.DrawFn) -> LengthOfStayRule:
    months = sorted(draw(st.sets(st.integers(2, 24), min_size=1, max_size=3)))
    return LengthOfStayRule(tuple(StayTier(month, -draw(BPS)) for month in months))


@st.composite
def override_rules(draw: st.DrawFn) -> OverrideRule:
    start = draw(DAYS)
    return OverrideRule(
        start,
        start + timedelta(days=draw(st.integers(0, 120))),
        Paise(draw(st.integers(1, 10_000_000))),
    )


DISCOUNT_RULES = st.one_of(
    st.builds(EarlyBirdRule, st.integers(1, 200), BPS.map(lambda bps: -bps)),
    st.builds(LastMinuteRule, st.integers(0, 60), st.integers(0, 9_999), BPS.map(lambda bps: -bps)),
    length_of_stay_rules(),
)
RULE_PARAMS = st.one_of(season_rules(), occupancy_rules(), DISCOUNT_RULES, override_rules())


@st.composite
def rules(draw: st.DrawFn, params: st.SearchStrategy[object] = RULE_PARAMS) -> PricingRule:
    categories = draw(
        st.one_of(st.none(), st.just(frozenset({CATEGORY})), st.just(frozenset({CATEGORY + 1})))
    )
    return PricingRule(
        draw(st.sampled_from(("Peak season", "Early-bird", "Long stay", "Quiet weeks"))),
        draw(params),  # type: ignore[arg-type]
        room_category_ids=categories,
        enabled=draw(st.booleans()),
    )


@st.composite
def bands(draw: st.DrawFn) -> RentBand:
    low = draw(st.integers(1, 3_000_000))
    return RentBand(
        Paise(low), Paise(low + draw(st.integers(0, 3_000_000))), BandSource.INTERNAL, ""
    )


@st.composite
def contexts(draw: st.DrawFn) -> PricingContext:
    today = draw(DAYS)
    return PricingContext(
        room_category_id=CATEGORY,
        base_rent_paise=Paise(draw(st.integers(1, 10_000_000))),
        owner_min_paise=draw(st.one_of(st.none(), st.integers(1, 5_000_000).map(Paise))),
        owner_max_paise=draw(st.one_of(st.none(), st.integers(1, 10_000_000).map(Paise))),
        move_in=today + timedelta(days=draw(st.integers(0, 400))),
        stay_months=draw(st.integers(1, 24)),
        today=today,
        occupancy_bps=draw(st.integers(0, 10_000)),
        rules=tuple(draw(st.lists(rules(), max_size=6))),
        band=draw(st.one_of(st.none(), bands())),
        fee_policy=FeePolicy(
            rate_bps=BasisPoints(draw(st.integers(0, 10_000))),
            basis=FeeBasis.LISTED_RENT,
            gst_rate_bps=BasisPoints(draw(st.integers(0, 10_000))),
            gst_mode=draw(st.sampled_from(GstMode)),
        ),
        booking_policy=dataclasses.replace(
            BOOKING, token_paise=Paise(draw(st.integers(100_000, 200_000)))
        ),
        caps=PricingCaps(
            max_premium_bps=BasisPoints(draw(st.integers(0, 10_000))),
            max_discount_bps=BasisPoints(draw(st.integers(0, 9_000))),
            rounding_step_paise=Paise(draw(st.integers(1, 1_000)) * 100),
        ),
    )


def quotable(ctx: PricingContext) -> Quote:
    """The quote, for contexts whose bounds leave a rent; the others are refused, and skipped."""
    low, high = bounds(ctx)
    if high is not None and low > high:
        with pytest.raises(ImpossibleBoundsError):
            quote(ctx)
        assume(False)
    return quote(ctx)


@given(contexts(), contexts())
def test_the_fee_depends_only_on_the_listed_rent_and_the_fee_policy(
    first: PricingContext, other: PricingContext
) -> None:
    # Everything else differs: rules, occupancy, dates, the stay, caps, band and owner bounds.
    second = dataclasses.replace(
        other, base_rent_paise=first.base_rent_paise, fee_policy=first.fee_policy
    )
    one, two = quotable(first), quotable(second)

    assert (one.fee_paise, one.gst_paise, one.owner_fee_total_paise) == (
        two.fee_paise,
        two.gst_paise,
        two.owner_fee_total_paise,
    )


@given(contexts())
def test_the_price_stays_inside_the_bounds_on_a_step_unless_none_fits(ctx: PricingContext) -> None:
    result = quotable(ctx)
    low, high = bounds(ctx)
    step = ctx.caps.rounding_step_paise
    price = result.monthly_rent_paise

    assert price >= low
    assert high is None or price <= high
    step_fits = high is None or -(-low // step) * step <= high
    if step_fits:
        assert price % step == 0


@given(contexts())
def test_premiums_and_discounts_stay_within_their_caps(ctx: PricingContext) -> None:
    result = quotable(ctx)

    assert 0 <= result.premium_bps <= ctx.caps.max_premium_bps
    assert 0 <= result.discount_bps <= ctx.caps.max_discount_bps


@given(contexts(), rules(DISCOUNT_RULES))
def test_early_bird_last_minute_and_long_stays_never_raise_a_price(
    ctx: PricingContext, discount: PricingRule
) -> None:
    before = quotable(ctx)
    after = quote(dataclasses.replace(ctx, rules=(*ctx.rules, discount)))

    assert after.monthly_rent_paise <= before.monthly_rent_paise


@given(contexts(), occupancy_rules())
def test_an_occupancy_premium_applies_only_at_or_above_its_threshold(
    ctx: PricingContext, rule: OccupancyRule
) -> None:
    result = quotable(dataclasses.replace(ctx, rules=(PricingRule("Busy", rule),)))
    applied = [item for item in result.adjustments if item.kind is RuleKind.OCCUPANCY]

    reached = [tier for tier in rule.tiers if tier.min_occupancy_bps <= ctx.occupancy_bps]
    assert [item.bps for item in applied] == ([reached[-1].bps] if reached else [])


@given(contexts())
def test_a_quote_is_the_same_every_time_in_whole_non_negative_paise(ctx: PricingContext) -> None:
    result = quotable(ctx)
    amounts = (
        result.monthly_rent_paise,
        result.fee_paise,
        result.gst_paise,
        result.owner_fee_total_paise,
        result.token_paise,
        result.due_at_move_in_paise,
    )

    assert quote(ctx) == result
    assert all(type(amount) is int and amount >= 0 for amount in amounts)
    assert result.due_at_move_in_paise + result.token_paise == result.monthly_rent_paise
    assert result.token_paise <= ctx.booking_policy.token_paise
    if ctx.fee_policy.gst_mode is GstMode.INCLUSIVE:
        assert result.owner_fee_total_paise == result.fee_paise
        assert result.gst_paise <= result.fee_paise
    else:
        assert result.owner_fee_total_paise == result.fee_paise + result.gst_paise
