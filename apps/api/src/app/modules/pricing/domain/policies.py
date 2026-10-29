"""The policies money follows (ARCHITECTURE §6 and §8, PRODUCT_CONTEXT §3 and §9; step 4.1, ADR
0036): the owner's placement fee, the booking terms a student relies on, the caps on dynamic
prices, and locality rent bands (CLAUDE.md rules 2, 3, 6, 8 and 9). Pure.

Each lives in a versioned table that admins change, never in code: a change starts a new version
from that moment and ends the one before, so a quote can always say which version priced it. The
tables start with PRODUCT_CONTEXT §9's defaults, seeded by a data migration. What follows says
what a version may hold, with the founders' rules as its limits.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from app.core.money import BasisPoints, Paise, rupees


class PolicyKind(StrEnum):
    FEE = "fee"
    BOOKING = "booking"
    CAPS = "caps"


class FeeBasis(StrEnum):
    # The room category's listed monthly rent: never a dynamic or peak price (rule 2).
    LISTED_RENT = "listed_rent"


class GstMode(StrEnum):
    # GST is added to the fee.
    EXCLUSIVE = "exclusive"
    # The fee already includes GST.
    INCLUSIVE = "inclusive"


class LateCancelPolicy(StrEnum):
    """Who keeps the token when a student cancels later than the free-cancellation days before
    moving in."""

    REFUND_FULL = "refund_full"
    FORFEIT_TO_OWNER = "forfeit_to_owner"
    SPLIT = "split"


class BandSource(StrEnum):
    # A rent band the authorities set (the Delhi PG bill's area-wise bands, once in force).
    OFFICIAL = "official"
    # One ops set from the market.
    INTERNAL = "internal"


@dataclass(frozen=True, slots=True)
class FeePolicy:
    rate_bps: BasisPoints
    basis: FeeBasis
    gst_rate_bps: BasisPoints
    gst_mode: GstMode


@dataclass(frozen=True, slots=True)
class BookingPolicy:
    token_paise: Paise
    hold_minutes: int
    free_cancel_days: int
    check_window_hours: int
    confirm_deadline_hours: int
    # An owner may mark a student who hasn't moved in this many days after the date.
    no_show_days: int
    late_cancel_policy: LateCancelPolicy
    max_active_holds_per_user: int
    # How far ahead a move-in may be booked.
    max_advance_days: int


@dataclass(frozen=True, slots=True)
class PricingCaps:
    max_premium_bps: BasisPoints
    max_discount_bps: BasisPoints
    rounding_step_paise: Paise


@dataclass(frozen=True, slots=True)
class RentBand:
    min_rent_paise: Paise
    max_rent_paise: Paise
    source: BandSource
    # Where an official band comes from (a notification's number or link), or ops' note on an
    # internal one.
    reference: str


FULL_BPS: Final = 10_000
# Rule 8: a token from ₹1,000 to ₹2,000 (PRODUCT_CONTEXT §3): UPI payments to merchants above
# ₹2,000 carry a fee that can't be passed on.
MIN_TOKEN: Final = rupees(1_000)
MAX_TOKEN: Final = rupees(2_000)
# A month's rent no PG in Delhi NCR comes near: a typing mistake, not a band.
MAX_RENT: Final = rupees(2_00_000)
REFERENCE_MAX_LENGTH: Final = 300
NOTE_MAX_LENGTH: Final = 500
# (lowest, highest) for each whole-number booking term, with what it is called.
_BOOKING_RANGES: Final = {
    "hold_minutes": (5, 60, "a bed's hold"),
    "free_cancel_days": (0, 60, "free cancellation"),
    "check_window_hours": (1, 168, "the check window"),
    "confirm_deadline_hours": (1, 72, "the owner's time to confirm"),
    "no_show_days": (1, 30, "the no-show wait"),
    "max_active_holds_per_user": (1, 3, "holds at once"),
    "max_advance_days": (1, 365, "how far ahead"),
}


def _bps_problem(what: str, value: int, *, top: int = FULL_BPS) -> list[str]:
    return [] if 0 <= value <= top else [f"{what} must be from 0 to {top / 100:g}%"]


def fee_problems(policy: FeePolicy) -> list[str]:
    return [
        *_bps_problem("the fee", policy.rate_bps),
        *_bps_problem("GST", policy.gst_rate_bps),
    ]


def booking_problems(policy: BookingPolicy) -> list[str]:
    problems = []
    if not MIN_TOKEN <= policy.token_paise <= MAX_TOKEN:
        problems.append("the token must be from ₹1,000 to ₹2,000")
    for field, (lowest, highest, what) in _BOOKING_RANGES.items():
        value = getattr(policy, field)
        if not lowest <= value <= highest:
            problems.append(f"{what} must be from {lowest} to {highest}")
    if policy.late_cancel_policy is not LateCancelPolicy.REFUND_FULL:
        # Paying a kept token to an owner needs Razorpay Route (PRODUCT_CONTEXT §9).
        problems.append("only refund_full works until payments go through Razorpay Route")
    return problems


def caps_problems(caps: PricingCaps) -> list[str]:
    problems = [
        *_bps_problem("the premium cap", caps.max_premium_bps),
        # A discount of 100% or more would give beds away.
        *_bps_problem("the discount cap", caps.max_discount_bps, top=FULL_BPS - 1_000),
    ]
    step = caps.rounding_step_paise
    if not rupees(1) <= step <= rupees(1_000) or step % rupees(1) != 0:
        problems.append("the rounding step must be whole rupees, from ₹1 to ₹1,000")
    return problems


def band_problems(band: RentBand) -> list[str]:
    problems = []
    if not 0 < band.min_rent_paise <= band.max_rent_paise:
        problems.append("the lowest rent must be above zero and no more than the highest")
    if band.max_rent_paise > MAX_RENT:
        problems.append("the highest rent must be no more than ₹2,00,000")
    if band.source is BandSource.OFFICIAL and not band.reference.strip():
        problems.append("an official band needs its reference: the notification it comes from")
    if len(band.reference) > REFERENCE_MAX_LENGTH:
        problems.append(f"the reference must be at most {REFERENCE_MAX_LENGTH} characters")
    return problems
