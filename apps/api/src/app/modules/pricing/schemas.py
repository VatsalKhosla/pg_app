"""Bodies of the pricing routes (camelCase JSON). Amounts are integer paise and rates basis
points (rule 12): the web app formats them and never works money out itself."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from app.core.schemas import ApiModel
from app.modules.catalog.domain.rooms import Occupancy
from app.modules.pricing.domain.engine import LABEL_MAX_LENGTH, RuleKind
from app.modules.pricing.domain.policies import (
    NOTE_MAX_LENGTH,
    REFERENCE_MAX_LENGTH,
    BandSource,
    FeeBasis,
    GstMode,
    LateCancelPolicy,
)
from app.modules.pricing.domain.rule_sets import RuleSetStatus


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


# Admins (ADR 0036).

Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=NOTE_MAX_LENGTH)]
# Generous bounds the domain's own limits sit inside; it names what's wrong in words.
Bps = Annotated[int, Field(ge=0, le=100_000)]
Count = Annotated[int, Field(ge=0, le=100_000)]
Amount = Annotated[int, Field(ge=0, le=1_000_000_000)]


class Changer(ApiModel):
    id: uuid.UUID
    name: str | None


class VersionMeta(ApiModel):
    id: uuid.UUID
    effective_from: datetime
    # Open while it's the version in force.
    effective_to: datetime | None
    changed_by: Changer | None
    note: str


class FeePolicyInput(ApiModel):
    """The next fee policy, in force from now. Why it changed goes in ``note``."""

    rate_bps: Bps
    basis: FeeBasis = FeeBasis.LISTED_RENT
    gst_rate_bps: Bps
    gst_mode: GstMode
    note: Note = ""


class FeePolicyVersionInfo(VersionMeta):
    rate_bps: int
    basis: FeeBasis
    gst_rate_bps: int
    gst_mode: GstMode


class BookingPolicyInput(ApiModel):
    token_paise: Amount
    hold_minutes: Count
    free_cancel_days: Count
    check_window_hours: Count
    confirm_deadline_hours: Count
    no_show_days: Count
    late_cancel_policy: LateCancelPolicy
    max_active_holds_per_user: Count
    max_advance_days: Count
    note: Note = ""


class BookingPolicyVersionInfo(VersionMeta):
    token_paise: int
    hold_minutes: int
    free_cancel_days: int
    check_window_hours: int
    confirm_deadline_hours: int
    no_show_days: int
    late_cancel_policy: LateCancelPolicy
    max_active_holds_per_user: int
    max_advance_days: int


class PricingCapsInput(ApiModel):
    max_premium_bps: Bps
    max_discount_bps: Bps
    rounding_step_paise: Amount
    note: Note = ""


class PricingCapsVersionInfo(VersionMeta):
    max_premium_bps: int
    max_discount_bps: int
    rounding_step_paise: int


class AdminPolicies(ApiModel):
    """Each policy's version in force."""

    fee: FeePolicyVersionInfo
    booking: BookingPolicyVersionInfo
    caps: PricingCapsVersionInfo


class PolicyHistory(ApiModel):
    """Each policy's latest versions, newest first."""

    fee: list[FeePolicyVersionInfo]
    booking: list[BookingPolicyVersionInfo]
    caps: list[PricingCapsVersionInfo]


class BandLocality(ApiModel):
    slug: str
    name: str


class RentBandInput(ApiModel):
    """A band for one locality and occupancy, in force from now; the one before ends."""

    locality: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=80)
    occupancy: Occupancy
    min_rent_paise: Amount
    max_rent_paise: Amount
    source: BandSource
    # An official band's notification (number or link); ops' note on an internal one.
    reference: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=REFERENCE_MAX_LENGTH)
    ] = ""
    note: Note = ""


class RentBandInfo(VersionMeta):
    locality: BandLocality
    occupancy: Occupancy
    min_rent_paise: int
    max_rent_paise: int
    source: BandSource
    reference: str


class RentBandList(ApiModel):
    items: list[RentBandInfo]


class RentBandEnd(ApiModel):
    note: Note = ""


# Rule sets (ADR 0038).

MonthDayText = Annotated[str, StringConstraints(pattern=r"^\d{2}-\d{2}$")]
RuleBps = Annotated[int, Field(ge=-10_000, le=10_000)]


class SeasonRuleParams(ApiModel):
    """Up or down by ``bps`` for move-ins from ``start`` to ``end`` (MM-DD, both included); may
    wrap the year."""

    kind: Literal["season"]
    start: MonthDayText
    end: MonthDayText
    bps: RuleBps


class OccupancyRuleTier(ApiModel):
    min_occupancy_bps: int = Field(ge=0, le=10_000)
    bps: RuleBps


class OccupancyRuleParams(ApiModel):
    """A premium from the highest tier the category's occupancy reaches."""

    kind: Literal["occupancy"]
    tiers: list[OccupancyRuleTier] = Field(min_length=1, max_length=5)


class EarlyBirdRuleParams(ApiModel):
    kind: Literal["early_bird"]
    min_days_before: int = Field(ge=0, le=365)
    bps: RuleBps


class LastMinuteRuleParams(ApiModel):
    kind: Literal["last_minute"]
    max_days_before: int = Field(ge=0, le=365)
    max_occupancy_bps: int = Field(ge=0, le=10_000)
    bps: RuleBps


class StayRuleTier(ApiModel):
    min_months: int = Field(ge=1, le=36)
    bps: RuleBps


class LengthOfStayRuleParams(ApiModel):
    """A discount from the highest tier the stay reaches."""

    kind: Literal["length_of_stay"]
    tiers: list[StayRuleTier] = Field(min_length=1, max_length=5)


class OverrideRuleParams(ApiModel):
    """A fixed monthly rent for move-ins from ``start`` to ``end``, both included."""

    kind: Literal["override"]
    start: date
    end: date
    rent_paise: Amount


RuleParamsBody = Annotated[
    SeasonRuleParams
    | OccupancyRuleParams
    | EarlyBirdRuleParams
    | LastMinuteRuleParams
    | LengthOfStayRuleParams
    | OverrideRuleParams,
    Field(discriminator="kind"),
]


class PricingRuleInput(ApiModel):
    # What students see, such as "Peak season".
    label: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=LABEL_MAX_LENGTH)
    ]
    params: RuleParamsBody
    # The PG's room categories it's for; null for all of them.
    room_categories: list[uuid.UUID] | None = Field(default=None, max_length=20)
    enabled: bool = True


class RuleCategory(ApiModel):
    id: uuid.UUID
    label: str


class PricingRuleInfo(ApiModel):
    id: uuid.UUID
    position: int
    kind: RuleKind
    label: str
    params: RuleParamsBody
    room_categories: list[RuleCategory] | None
    enabled: bool


class RuleSetProperty(ApiModel):
    id: uuid.UUID
    name: str


class RuleSetInfo(ApiModel):
    id: uuid.UUID
    version: int
    status: RuleSetStatus
    property: RuleSetProperty
    activated_at: datetime | None
    activated_by: Changer | None
    archived_at: datetime | None
    note: str
    rules: list[PricingRuleInfo]
    # What stops a draft going into force, in words; empty when it may.
    problems: list[str]


class RuleSetSummaryInfo(ApiModel):
    id: uuid.UUID
    version: int
    status: RuleSetStatus
    activated_at: datetime | None
    archived_at: datetime | None
    note: str
    rules: int


class RuleSetList(ApiModel):
    property: RuleSetProperty
    items: list[RuleSetSummaryInfo]


class RuleSetActivation(ApiModel):
    note: Note = ""
