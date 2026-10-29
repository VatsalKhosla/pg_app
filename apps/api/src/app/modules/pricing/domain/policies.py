"""The policies money follows (ARCHITECTURE §6, PRODUCT_CONTEXT §3 and §9): the owner's placement
fee, and the booking terms a student relies on (CLAUDE.md rules 2, 3, 8 and 9). Pure.

Step 4.1 keeps these in ``fee_policies`` and ``booking_policies``, which admins edit with an audit
trail; until then the current policies are the defaults those tables will be seeded with. The
founders' open decisions (whether the fee includes GST, the token, late cancellation) are settings
there, never code.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from app.core.money import BasisPoints, Paise, rupees


class FeeBasis(StrEnum):
    # The room category's listed monthly rent: never a dynamic or peak price (rule 2).
    LISTED_RENT = "listed_rent"


class GstMode(StrEnum):
    # GST is added to the fee.
    EXCLUSIVE = "exclusive"
    # The fee already includes GST.
    INCLUSIVE = "inclusive"


class LateCancelPolicy(StrEnum):
    """Who keeps the token when a student cancels less than the free-cancellation days before
    moving in."""

    REFUND_FULL = "refund_full"
    FORFEIT_TO_OWNER = "forfeit_to_owner"
    SPLIT = "split"


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
    late_cancel_policy: LateCancelPolicy


# Rule 8: a token never above ₹2,000 (UPI payments to merchants above it carry a fee).
MAX_TOKEN: Final = rupees(2_000)

DEFAULT_FEE_POLICY: Final = FeePolicy(
    rate_bps=BasisPoints(3_000),
    basis=FeeBasis.LISTED_RENT,
    gst_rate_bps=BasisPoints(1_800),
    gst_mode=GstMode.EXCLUSIVE,
)
DEFAULT_BOOKING_POLICY: Final = BookingPolicy(
    token_paise=rupees(2_000),
    hold_minutes=15,
    free_cancel_days=7,
    check_window_hours=24,
    confirm_deadline_hours=12,
    # refund_full until Razorpay Route can pay a forfeited token to an owner (PRODUCT_CONTEXT §9).
    late_cancel_policy=LateCancelPolicy.REFUND_FULL,
)
