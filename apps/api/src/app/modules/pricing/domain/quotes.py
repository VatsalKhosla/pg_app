"""Quotes (ARCHITECTURE §8.4; step 4.4, ADR 0039). Pure.

A quote is the engine's answer for one room category, move-in and stay, kept with everything
that made it: the versions of the rules and policies, the engine's version and a hash of the
inputs, so it can be explained and checked later. It stands for 30 minutes; a booking (Phase 5)
copies its money and the rent stays fixed for the whole stay (rule 5).
"""

import hashlib
import json
from datetime import date, timedelta
from typing import TYPE_CHECKING, Final

from app.core.money import format_rupees
from app.modules.pricing.domain.engine import PricingContext, Quote, RuleKind
from app.modules.pricing.domain.rule_sets import params_to_json

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.modules.pricing.domain.policies import BookingPolicy

QUOTE_TTL: Final = timedelta(minutes=30)
MAX_STAY_MONTHS: Final = 36
# A real minus sign for people, rather than a hyphen.
_MINUS: Final = chr(0x2212)


def quote_problems(
    *, move_in: date, stay_months: int, today: date, booking: BookingPolicy
) -> list[str]:
    """What stops a quote for this move-in and stay; empty when nothing does."""
    problems = []
    if move_in < today:
        problems.append("the move-in date has passed")
    elif move_in > today + timedelta(days=booking.max_advance_days):
        problems.append(f"a move-in can be booked at most {booking.max_advance_days} days ahead")
    if not 1 <= stay_months <= MAX_STAY_MONTHS:
        problems.append(f"a stay is from 1 to {MAX_STAY_MONTHS} months")
    return problems


def bps_text(bps: int) -> str:
    """A rule's move as people read it: +15%, +2.5%, or a minus sign and 5%."""
    whole, rest = divmod(abs(bps), 100)
    number = str(whole) if rest == 0 else f"{whole}.{rest:02d}".rstrip("0")
    return f"{'+' if bps >= 0 else _MINUS}{number}%"


def explanation(quote: Quote) -> str:
    """The quote in one line (§8.4), such as "Base ₹10,000 · Peak season +15% · Early-bird
    (minus) 5% = ₹11,000/month, fixed for your stay"."""
    parts = [f"Base {format_rupees(quote.base_rent_paise)}"]
    for adjustment in quote.adjustments:
        if adjustment.kind is RuleKind.OVERRIDE and adjustment.rent_paise is not None:
            parts.append(f"{adjustment.label} {format_rupees(adjustment.rent_paise)}")
        elif adjustment.bps is not None:
            parts.append(f"{adjustment.label} {bps_text(adjustment.bps)}")
    rent = format_rupees(quote.monthly_rent_paise)
    return f"{' · '.join(parts)} = {rent}/month, fixed for your stay"


def inputs_digest(context: PricingContext, *, versions: Mapping[str, str | int | None]) -> str:
    """A SHA-256 of everything the quote was worked out from, in a canonical form: the same
    inputs give the same digest, and any change, however small, another."""
    band = context.band
    inputs = {
        "category": context.room_category_id,
        "base": context.base_rent_paise,
        "owner": [context.owner_min_paise, context.owner_max_paise],
        "move_in": context.move_in.isoformat(),
        "stay": context.stay_months,
        "today": context.today.isoformat(),
        "occupancy": context.occupancy_bps,
        "rules": [
            {
                "kind": rule.kind,
                "label": rule.label,
                "params": params_to_json(rule.params),
                "categories": None
                if rule.room_category_ids is None
                else sorted(rule.room_category_ids),
                "enabled": rule.enabled,
            }
            for rule in context.rules
        ],
        "band": None if band is None else [band.min_rent_paise, band.max_rent_paise],
        "fee": [
            context.fee_policy.rate_bps,
            context.fee_policy.basis,
            context.fee_policy.gst_rate_bps,
            context.fee_policy.gst_mode,
        ],
        "token": context.booking_policy.token_paise,
        "caps": [
            context.caps.max_premium_bps,
            context.caps.max_discount_bps,
            context.caps.rounding_step_paise,
        ],
        "versions": dict(sorted(versions.items())),
    }
    canonical = json.dumps(inputs, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()
