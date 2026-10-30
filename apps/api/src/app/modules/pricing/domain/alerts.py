"""Pricing's integrity alerts (ARCHITECTURE §8.7; step 4.8, ADR 0043). Pure.

What ops should look at, each raised once for what it's about, however often the checks run:
- a room's listed rent more than 25% below the median listed rent for its sharing in its
  locality's other published PGs, once there are enough of them to compare with;
- a PG whose quotes a limit held back (a cap, the owner's limits or the band) more than 20% of
  the time in a week, once there are enough quotes to say so;
- a PG whose rules went into force more than three times in a week: prices that keep moving
  confuse students, and can hide trouble.
"""

from datetime import date, timedelta
from enum import StrEnum
from typing import Final

from app.core.money import BPS_PER_WHOLE

# ARCHITECTURE §8.7: more than 25% below the locality's median, and clamps on more than 20% of
# a week's quotes.
BELOW_MARKET_BPS: Final = 2_500
CLAMPED_SHARE_BPS: Final = 2_000
# Fewer comparables or quotes than these say too little to alert on.
MIN_COMPARABLES: Final = 3
MIN_WEEKLY_QUOTES: Final = 10
# Rules going into force more often than this in a week is churn.
MAX_WEEKLY_ACTIVATIONS: Final = 3
RESOLUTION_MAX_LENGTH: Final = 500


class AlertKind(StrEnum):
    RENT_BELOW_MARKET = "rent_below_market"
    CLAMPS_FREQUENT = "clamps_frequent"
    RULE_CHURN = "rule_churn"


def below_market(rent: int, median: int | None, comparables: int) -> bool:
    """Whether a listed rent is more than 25% below the median, with enough to compare with."""
    if median is None or comparables < MIN_COMPARABLES:
        return False
    return rent * BPS_PER_WHOLE < median * (BPS_PER_WHOLE - BELOW_MARKET_BPS)


def clamps_frequent(quotes: int, clamped: int) -> bool:
    """Whether more than 20% of a week's quotes were held back, with enough quotes to say so."""
    return quotes >= MIN_WEEKLY_QUOTES and clamped * BPS_PER_WHOLE > quotes * CLAMPED_SHARE_BPS


def churning(activations: int) -> bool:
    """Whether a week's activations of a PG's rules are too many."""
    return activations > MAX_WEEKLY_ACTIVATIONS


def week_of(day: date) -> date:
    """The Monday that starts ``day``'s week."""
    return day - timedelta(days=day.weekday())


def alert_key(kind: AlertKind, *about: object) -> str:
    """What makes an alert this alert: it's raised once for it, and never again.

    A rent below the market is about a room at one listed rent (a new rent that's also too low
    is a new alert); clamps and churn are about a PG in one week.
    """
    return ":".join([kind.value, *(str(part) for part in about)])
