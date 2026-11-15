"""Sign-in codes (ARCHITECTURE §12, ADR 0068): where a code goes, how long it lives, how often it
may be tried, and how often a new one may be sent.

A code is six digits. It goes to a phone by text, or to an email address, and lasts five minutes
on a phone and ten in an inbox (mail can take a while to arrive). Five wrong tries lock it, so
the sixth attempt fails whatever it says. Asking for a new code replaces the previous one, at
most every 30 seconds.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

CODE_DIGITS: Final = 6
CODE_TTL: Final = timedelta(minutes=5)
EMAIL_CODE_TTL: Final = timedelta(minutes=10)
MAX_ATTEMPTS: Final = 5
RESEND_COOLDOWN: Final = timedelta(seconds=30)
# The Turnstile action the sign-in form's widget sets; a token solved for another form fails.
HUMAN_CHECK_ACTION: Final = "otp_request"


class OtpPurpose(StrEnum):
    SIGN_IN = "sign_in"


class Channel(StrEnum):
    PHONE = "phone"
    EMAIL = "email"


@dataclass(frozen=True, slots=True)
class Destination:
    """Where a code goes: a phone (E.164) or an email address (lowercase)."""

    channel: Channel
    address: str

    @property
    def code_ttl(self) -> timedelta:
        return EMAIL_CODE_TTL if self.channel is Channel.EMAIL else CODE_TTL


class ChallengeState(StrEnum):
    OPEN = "open"
    # Used up: verified already, or replaced by a newer code.
    USED = "used"
    LOCKED = "locked"
    EXPIRED = "expired"


def challenge_state(
    *,
    now: datetime,
    expires_at: datetime,
    attempts: int,
    consumed_at: datetime | None,
    superseded_at: datetime | None,
) -> ChallengeState:
    if consumed_at is not None or superseded_at is not None:
        return ChallengeState.USED
    if attempts >= MAX_ATTEMPTS:
        return ChallengeState.LOCKED
    if now >= expires_at:
        return ChallengeState.EXPIRED
    return ChallengeState.OPEN


def resend_wait(*, now: datetime, last_requested_at: datetime | None) -> timedelta:
    """How long until another code may be sent to the same phone or address."""
    if last_requested_at is None:
        return timedelta(0)
    return max(timedelta(0), last_requested_at + RESEND_COOLDOWN - now)


def attempts_left(attempts: int) -> int:
    return max(0, MAX_ATTEMPTS - attempts)
