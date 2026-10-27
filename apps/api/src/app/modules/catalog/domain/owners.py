"""PG owners (ARCHITECTURE §6): the businesses that list PGs and pay the placement fee.

An owner is a user account with an owner record: legal and business names, an optional GSTIN,
where KYC stands, the owner agreement they accepted last (step 2.6, ADR 0025), and the payout
account that split settlement pays into (CLAUDE.md rule 10).
"""

import re
from enum import StrEnum
from typing import Final

NAME_MAX_LENGTH: Final = 120
# State code, PAN, entity number, "Z", check character.
GSTIN_PATTERN: Final = re.compile(r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]")
# A GSTIN's characters by value, for its check character.
_GSTIN_CHARACTERS: Final = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


class OwnerStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class KycStatus(StrEnum):
    NOT_STARTED = "not_started"
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


def gstin_check_character(first_fourteen: str) -> str:
    """A GSTIN's last character, from the 14 before it: Luhn's check in base 36, as GSTN makes
    it. Every other value of each character changes it, so one mistyped character is caught."""
    total = 0
    for position, character in enumerate(first_fourteen):
        product = _GSTIN_CHARACTERS.index(character) * (2 if position % 2 else 1)
        total += product // 36 + product % 36
    return _GSTIN_CHARACTERS[-total % 36]


def normalize_gstin(raw: str) -> str | None:
    """A GSTIN as stored (capitals, no spaces), or None if it can't be one: the wrong shape, or a
    check character that doesn't match the rest."""
    gstin = re.sub(r"\s", "", raw).upper()
    if not GSTIN_PATTERN.fullmatch(gstin):
        return None
    return gstin if gstin[-1] == gstin_check_character(gstin[:-1]) else None
