"""Grievances (PRODUCT_CONTEXT §7; step 3.8, ADR 0034). The Consumer Protection (E-Commerce)
Rules, 2020 want a grievance officer who acknowledges a complaint within 48 hours and resolves it
within a month of receiving it. Anyone may complain, signed in or not, and gets a ticket number
at once.

A grievance is received, then acknowledged by the officer with a reply, then resolved with what
was done. Resolving one that hasn't been acknowledged acknowledges it too. Pure: callers pass
"now".
"""

from calendar import monthrange
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

from app.core.calendar import INDIA


class GrievanceStatus(StrEnum):
    RECEIVED = "received"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class GrievanceCategory(StrEnum):
    # A PG's details, photos, price or verification.
    LISTING = "listing"
    VISIT = "visit"
    # A booking, the token or a refund.
    BOOKING = "booking"
    # How an owner or a PG's staff behaved.
    OWNER = "owner"
    # How our own staff behaved.
    STAFF = "staff"
    # Personal data (the DPDP Act's grievances come here too).
    PRIVACY = "privacy"
    ACCOUNT = "account"
    OTHER = "other"


ACKNOWLEDGE_WITHIN: Final = timedelta(hours=48)
DETAILS_MAX_LENGTH: Final = 2000
REPLY_MAX_LENGTH: Final = 2000
NAME_MAX_LENGTH: Final = 100
REFERENCE_MAX_LENGTH: Final = 100
EMAIL_MAX_LENGTH: Final = 254

_NEXT: Final = {
    GrievanceStatus.RECEIVED: frozenset({GrievanceStatus.ACKNOWLEDGED, GrievanceStatus.RESOLVED}),
    GrievanceStatus.ACKNOWLEDGED: frozenset({GrievanceStatus.RESOLVED}),
}


def can_move(current: GrievanceStatus, target: GrievanceStatus) -> bool:
    return target in _NEXT.get(current, frozenset())


def acknowledge_by(received_at: datetime) -> datetime:
    return received_at + ACKNOWLEDGE_WITHIN


def resolve_by(received_at: datetime) -> datetime:
    """A calendar month after it was received, in India, at the same time of day; a day the
    next month doesn't have becomes its last (31 January's is 28 or 29 February)."""
    local = received_at.astimezone(INDIA)
    year, month = (local.year + 1, 1) if local.month == 12 else (local.year, local.month + 1)
    return local.replace(year=year, month=month, day=min(local.day, monthrange(year, month)[1]))


def is_late(status: GrievanceStatus, *, received_at: datetime, now: datetime) -> bool:
    """Whether the grievance is still waiting on a step whose deadline has passed."""
    if status is GrievanceStatus.RESOLVED:
        return False
    if status is GrievanceStatus.RECEIVED and now > acknowledge_by(received_at):
        return True
    return now > resolve_by(received_at)
