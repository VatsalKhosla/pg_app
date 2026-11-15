"""A booking's rent agreement (ADR 0070): its states, and who may sign it when. Pure.

Once its owner confirms a booking, the student and the owner each sign the same text, in either
order, each with a one-time code and their full name typed. The agreement is signed when both
have. If the booking ends early (cancelled, rejected, a no-show or refunded) before both have
signed, the agreement is void.

    awaiting_signatures ─ student signs ─▶ signed_by_student ─ owner signs ───▶ signed
             │          └─ owner signs ──▶ signed_by_owner ─── student signs ─▶ signed
             └─ booking ended early (from any of the first three) ──────────▶ void

Anything not drawn is refused: a second signature from one side, a signature on a void or signed
agreement, voiding a signed one. The text is the agreement's own until somebody signs; from the
first signature on, it never changes, so both sides sign exactly the same words.
"""

import re
import unicodedata
from enum import StrEnum
from typing import Final


class AgreementStatus(StrEnum):
    AWAITING_SIGNATURES = "awaiting_signatures"
    SIGNED_BY_STUDENT = "signed_by_student"
    SIGNED_BY_OWNER = "signed_by_owner"
    SIGNED = "signed"
    VOID = "void"


class Signer(StrEnum):
    """The two sides: the student who booked (the licensee) and the PG's owner (the licensor)."""

    STUDENT = "student"
    OWNER = "owner"


class AgreementEvent(StrEnum):
    STUDENT_SIGNS = "student_signs"
    OWNER_SIGNS = "owner_signs"
    # The booking ended before the stay began: cancelled, rejected, a no-show or refunded.
    BOOKING_ENDED_EARLY = "booking_ended_early"


SIGNS: Final = {
    Signer.STUDENT: AgreementEvent.STUDENT_SIGNS,
    Signer.OWNER: AgreementEvent.OWNER_SIGNS,
}

_TABLE: Final[dict[tuple[AgreementStatus, AgreementEvent], AgreementStatus]] = {
    (AgreementStatus.AWAITING_SIGNATURES, AgreementEvent.STUDENT_SIGNS): (
        AgreementStatus.SIGNED_BY_STUDENT
    ),
    (AgreementStatus.AWAITING_SIGNATURES, AgreementEvent.OWNER_SIGNS): (
        AgreementStatus.SIGNED_BY_OWNER
    ),
    (AgreementStatus.SIGNED_BY_STUDENT, AgreementEvent.OWNER_SIGNS): AgreementStatus.SIGNED,
    (AgreementStatus.SIGNED_BY_OWNER, AgreementEvent.STUDENT_SIGNS): AgreementStatus.SIGNED,
    (AgreementStatus.AWAITING_SIGNATURES, AgreementEvent.BOOKING_ENDED_EARLY): (
        AgreementStatus.VOID
    ),
    (AgreementStatus.SIGNED_BY_STUDENT, AgreementEvent.BOOKING_ENDED_EARLY): AgreementStatus.VOID,
    (AgreementStatus.SIGNED_BY_OWNER, AgreementEvent.BOOKING_ENDED_EARLY): AgreementStatus.VOID,
}
# Statuses no event leaves.
FINAL: Final = frozenset({AgreementStatus.SIGNED, AgreementStatus.VOID})
_SIGNED_BY: Final[dict[AgreementStatus, frozenset[Signer]]] = {
    AgreementStatus.AWAITING_SIGNATURES: frozenset(),
    AgreementStatus.SIGNED_BY_STUDENT: frozenset({Signer.STUDENT}),
    AgreementStatus.SIGNED_BY_OWNER: frozenset({Signer.OWNER}),
    AgreementStatus.SIGNED: frozenset(Signer),
    # Whoever had signed before it was voided is in the signatures, not the status.
    AgreementStatus.VOID: frozenset(),
}

_REFUSALS: Final = {
    AgreementStatus.SIGNED: "Both sides have signed this agreement already.",
    AgreementStatus.VOID: "This agreement is void: its booking ended before both sides signed.",
}


class AgreementRefusedError(Exception):
    """The agreement can't take this event in its current status (answered 409)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def transition(status: AgreementStatus, event: AgreementEvent) -> AgreementStatus:
    """The status after ``event``, or AgreementRefusedError with the reason."""
    found = _TABLE.get((status, event))
    if found is not None:
        return found
    if status in _REFUSALS:
        raise AgreementRefusedError(_REFUSALS[status])
    raise AgreementRefusedError("You've signed this agreement already.")


def signed_by(status: AgreementStatus) -> frozenset[Signer]:
    """Who has signed, as the status says (a void agreement's signatures are in its record)."""
    return _SIGNED_BY[status]


def awaits(status: AgreementStatus, signer: Signer) -> bool:
    """Whether ``signer`` may sign now."""
    return (status, SIGNS[signer]) in _TABLE


def text_settled(status: AgreementStatus) -> bool:
    """Whether the text is fixed for good: once anyone has signed, and once the agreement is void.
    Until then it follows the booking's facts and the template in force."""
    return status is not AgreementStatus.AWAITING_SIGNATURES


# A typed name, as people write theirs: letters and marks of any script, spaces, dots, apostrophes
# and hyphens. It's the signer's own act of signing, kept as typed once tidied.
TYPED_NAME_MIN: Final = 2
TYPED_NAME_MAX: Final = 80
_NAME_CHARACTERS: Final = re.compile(r"[^\W\d_]|[ .'\u2019-]")


def typed_name(raw: str) -> str | None:
    """``raw`` with its spaces tidied (NFC, single spaces, trimmed), or None when it isn't a name:
    too short or long, without a letter, or with digits or symbols."""
    name = " ".join(unicodedata.normalize("NFC", raw).split())
    if not TYPED_NAME_MIN <= len(name) <= TYPED_NAME_MAX:
        return None
    if not any(character.isalpha() for character in name):
        return None
    if not all(
        _NAME_CHARACTERS.fullmatch(character) or unicodedata.category(character).startswith("M")
        for character in name
    ):
        return None
    return name
