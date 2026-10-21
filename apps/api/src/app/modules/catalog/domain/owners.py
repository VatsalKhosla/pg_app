"""PG owners (ARCHITECTURE §6): the businesses that list PGs and pay the placement fee.

An owner is a user account with an owner record: legal and business names, an optional GSTIN,
where KYC stands, and the payout account that split settlement pays into (CLAUDE.md rule 10).
Step 2.6 adds their profiles, the GSTIN's check digit and the agreement.
"""

import re
from enum import StrEnum
from typing import Final

NAME_MAX_LENGTH: Final = 120
# State code, PAN, entity number, "Z", check character.
GSTIN_PATTERN: Final = re.compile(r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]")


class OwnerStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class KycStatus(StrEnum):
    NOT_STARTED = "not_started"
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


def normalize_gstin(raw: str) -> str | None:
    """A GSTIN as stored (capitals, no spaces), or None if it can't be one."""
    gstin = re.sub(r"\s", "", raw).upper()
    return gstin if GSTIN_PATTERN.fullmatch(gstin) else None
