"""A student's report that their room isn't as shown (step 5.7; ARCHITECTURE §6, §7.4): what it
says, and how ops settle it. The state machine decides when one may be opened or resolved; these
are the report's own rules."""

from enum import StrEnum
from typing import Final


class DisputeReason(StrEnum):
    # The room, its bed or what comes with it differs from the listing.
    NOT_AS_SHOWN = "not_as_shown"
    UNSAFE = "unsafe"
    OTHER = "other"


class DisputeStatus(StrEnum):
    OPEN = "open"
    # The bed was released and the token refunded in full.
    RESOLVED_REFUND = "resolved_refund"
    # The room was as shown: the stay goes ahead.
    RESOLVED_UPHOLD = "resolved_uphold"


class DisputeOutcome(StrEnum):
    """What ops decide."""

    REFUND = "refund"
    UPHOLD = "uphold"


# Enough to show the room; a report is read by a person.
MAX_PHOTOS: Final = 6
DESCRIPTION_MIN_LENGTH: Final = 10
DESCRIPTION_MAX_LENGTH: Final = 2_000
NOTES_MAX_LENGTH: Final = 1_000


def resolved(outcome: DisputeOutcome) -> DisputeStatus:
    return (
        DisputeStatus.RESOLVED_REFUND
        if outcome is DisputeOutcome.REFUND
        else DisputeStatus.RESOLVED_UPHOLD
    )


def photo_problems(photos: list[str]) -> list[str]:
    """What's wrong with a report's photos, by their ids: at most six, each once."""
    problems = []
    if len(photos) > MAX_PHOTOS:
        problems.append(f"at most {MAX_PHOTOS} photos")
    if len(set(photos)) != len(photos):
        problems.append("each photo once")
    return problems
