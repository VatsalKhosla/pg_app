"""The policies' limits (step 4.1, ADR 0036), without a database: what a version of the fee,
the booking terms, the caps or a rent band may hold, with the founders' rules as the limits."""

import dataclasses

import pytest

from app.core.money import BasisPoints, Paise, rupees
from app.modules.pricing.domain.policies import (
    BandSource,
    BookingPolicy,
    FeeBasis,
    FeePolicy,
    GstMode,
    LateCancelPolicy,
    PricingCaps,
    RentBand,
    band_problems,
    booking_problems,
    caps_problems,
    fee_problems,
)

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
BAND = RentBand(
    min_rent_paise=rupees(8_000),
    max_rent_paise=rupees(14_000),
    source=BandSource.INTERNAL,
    reference="",
)


def test_product_contexts_defaults_are_allowed() -> None:
    assert fee_problems(FEE) == []
    assert booking_problems(BOOKING) == []
    assert caps_problems(CAPS) == []
    assert band_problems(BAND) == []


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"rate_bps": BasisPoints(10_001)}, "the fee must be from 0 to 100%"),
        ({"gst_rate_bps": BasisPoints(-1)}, "GST must be from 0 to 100%"),
    ],
)
def test_a_fee_out_of_range_says_why(change: dict[str, object], problem: str) -> None:
    assert problem in fee_problems(dataclasses.replace(FEE, **change))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        # Rule 8: from ₹1,000 to ₹2,000.
        ({"token_paise": rupees(2_001)}, "the token must be from ₹1,000 to ₹2,000"),
        ({"token_paise": Paise(rupees(1_000) - 1)}, "the token must be from ₹1,000 to ₹2,000"),
        ({"hold_minutes": 61}, "a bed's hold must be from 5 to 60"),
        ({"free_cancel_days": -1}, "free cancellation must be from 0 to 60"),
        ({"max_active_holds_per_user": 0}, "holds at once must be from 1 to 3"),
        # Paying a kept token to an owner needs Razorpay Route (PRODUCT_CONTEXT §9).
        (
            {"late_cancel_policy": LateCancelPolicy.FORFEIT_TO_OWNER},
            "only refund_full works until payments go through Razorpay Route",
        ),
    ],
)
def test_booking_terms_out_of_range_say_why(change: dict[str, object], problem: str) -> None:
    assert problem in booking_problems(dataclasses.replace(BOOKING, **change))  # type: ignore[arg-type]


def test_the_token_may_be_anything_from_1000_to_2000_rupees() -> None:
    for token in (rupees(1_000), rupees(1_500), rupees(2_000)):
        assert booking_problems(dataclasses.replace(BOOKING, token_paise=token)) == []


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"max_premium_bps": BasisPoints(10_001)}, "the premium cap must be from 0 to 100%"),
        # A discount of 100% or more would give beds away.
        ({"max_discount_bps": BasisPoints(9_001)}, "the discount cap must be from 0 to 90%"),
        (
            {"rounding_step_paise": Paise(5_050)},
            "the rounding step must be whole rupees, from ₹1 to ₹1,000",
        ),
        (
            {"rounding_step_paise": rupees(1_001)},
            "the rounding step must be whole rupees, from ₹1 to ₹1,000",
        ),
    ],
)
def test_caps_out_of_range_say_why(change: dict[str, object], problem: str) -> None:
    assert problem in caps_problems(dataclasses.replace(CAPS, **change))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (
            {"min_rent_paise": rupees(15_000)},
            "the lowest rent must be above zero and no more than the highest",
        ),
        (
            {"min_rent_paise": Paise(0)},
            "the lowest rent must be above zero and no more than the highest",
        ),
        ({"max_rent_paise": rupees(2_00_001)}, "the highest rent must be no more than ₹2,00,000"),
        (
            {"source": BandSource.OFFICIAL, "reference": "  "},
            "an official band needs its reference: the notification it comes from",
        ),
        (
            {"reference": "x" * 301},
            "the reference must be at most 300 characters",
        ),
    ],
)
def test_bands_that_dont_work_say_why(change: dict[str, object], problem: str) -> None:
    assert problem in band_problems(dataclasses.replace(BAND, **change))  # type: ignore[arg-type]
