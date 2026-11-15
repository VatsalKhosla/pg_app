"""Signing codes (ADR 0070): the one-time code each side confirms their signature with. Pure.

A code is six digits, sent to the signer and kept only as a keyed digest. It lasts ten minutes,
long enough to read it out of an email, and five wrong tries lock it, so the sixth attempt fails
whatever it says. Asking again replaces the code, at most every 30 seconds; and a code signs one
agreement, for the one side that asked for it.
"""

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

CODE_DIGITS: Final = 6
CODE_TTL: Final = timedelta(minutes=10)
MAX_ATTEMPTS: Final = 5
RESEND_COOLDOWN: Final = timedelta(seconds=30)


class CodeState(StrEnum):
    OPEN = "open"
    # Used up: signed with already, or replaced by a newer code.
    USED = "used"
    LOCKED = "locked"
    EXPIRED = "expired"


def code_state(
    *,
    now: datetime,
    expires_at: datetime,
    attempts: int,
    consumed_at: datetime | None,
    superseded_at: datetime | None,
) -> CodeState:
    if consumed_at is not None or superseded_at is not None:
        return CodeState.USED
    if attempts >= MAX_ATTEMPTS:
        return CodeState.LOCKED
    if now >= expires_at:
        return CodeState.EXPIRED
    return CodeState.OPEN


def resend_wait(*, now: datetime, last_requested_at: datetime | None) -> timedelta:
    """How long until the same person may ask for another code for the same agreement."""
    if last_requested_at is None:
        return timedelta(0)
    return max(timedelta(0), last_requested_at + RESEND_COOLDOWN - now)


def attempts_left(attempts: int) -> int:
    return max(0, MAX_ATTEMPTS - attempts)
