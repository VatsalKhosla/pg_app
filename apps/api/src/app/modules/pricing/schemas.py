"""Bodies of the pricing routes (camelCase JSON). Amounts are integer paise and rates basis
points (rule 12): the web app formats them and never works money out itself."""

from app.core.schemas import ApiModel
from app.modules.pricing.domain.policies import FeeBasis, GstMode, LateCancelPolicy


class PlacementFeeTerms(ApiModel):
    """What an owner pays, once per tenant placed: ``rateBps`` of ``basis``, with GST at
    ``gstRateBps`` added (``exclusive``) or included (``inclusive``)."""

    rate_bps: int
    basis: FeeBasis
    gst_rate_bps: int
    gst_mode: GstMode


class BookingTerms(ApiModel):
    """What a student relies on when they reserve a bed."""

    # The refundable token, which counts toward the first month's rent.
    token_paise: int
    # A bed is held this long while the student pays the token.
    hold_minutes: int
    # Cancelling at least this many days before moving in is free.
    free_cancel_days: int
    # After moving in, the student has this long to say the room isn't as shown.
    check_window_hours: int
    # The owner confirms a reservation within this, or the token is refunded.
    confirm_deadline_hours: int
    # Who keeps the token after a later cancellation.
    late_cancel_policy: LateCancelPolicy


class PublicPolicies(ApiModel):
    """The terms in force, as the Pricing and token pages explain them. Students never pay a
    platform fee (rule 1), so there is no student fee to state."""

    placement_fee: PlacementFeeTerms
    booking: BookingTerms
