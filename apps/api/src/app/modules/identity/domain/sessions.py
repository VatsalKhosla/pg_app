"""Session lifetimes (ARCHITECTURE §12): when a session expires and when its expiry slides.

Students, parents and owners keep a session for 30 days after they were last seen. Staff
sessions end 12 hours after sign-in, however active they are. A session's expiry moves forward at
most every 10 minutes, so a busy session doesn't write to the database on every request.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final


class SessionKind(StrEnum):
    USER = "user"
    STAFF = "staff"


class EndReason(StrEnum):
    """Why a session ended before its expiry."""

    LOGOUT = "logout"
    LOGOUT_EVERYWHERE = "logout_everywhere"
    # Signed out from the session list on another device.
    ENDED_BY_USER = "ended_by_user"
    # A new sign-in on the same browser replaced it.
    REPLACED = "replaced"


@dataclass(frozen=True)
class SessionPolicy:
    # Inactivity after which the session ends.
    idle_ttl: timedelta
    # The longest a session may last from sign-in, however active; None for no limit.
    absolute_ttl: timedelta | None
    # How often activity moves the expiry forward.
    touch_interval: timedelta


POLICIES: Final = {
    SessionKind.USER: SessionPolicy(
        idle_ttl=timedelta(days=30), absolute_ttl=None, touch_interval=timedelta(minutes=10)
    ),
    SessionKind.STAFF: SessionPolicy(
        idle_ttl=timedelta(hours=12),
        absolute_ttl=timedelta(hours=12),
        touch_interval=timedelta(minutes=10),
    ),
}


def absolute_expiry(policy: SessionPolicy, *, started_at: datetime) -> datetime | None:
    return None if policy.absolute_ttl is None else started_at + policy.absolute_ttl


def sliding_expiry(
    policy: SessionPolicy, *, now: datetime, absolute_expires_at: datetime | None
) -> datetime:
    """The expiry after activity at ``now``, never beyond the absolute limit."""
    sliding = now + policy.idle_ttl
    return sliding if absolute_expires_at is None else min(sliding, absolute_expires_at)


def is_due_for_touch(policy: SessionPolicy, *, now: datetime, last_seen_at: datetime) -> bool:
    return now - last_seen_at >= policy.touch_interval
