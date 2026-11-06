"""An owner's documents for a PG (step 7.1, ADR 0063). Pure.

Owners upload them; ops read them and say whether they're good. Nothing here decides what the law
requires of a PG: that's for the founders and their lawyer.
"""

from enum import StrEnum


class DocumentKind(StrEnum):
    # The PG's licence or registration, where the city asks for one.
    LICENCE = "licence"
    # The housing society's permission to run a PG, where the building is in one.
    SOCIETY_PERMISSION = "society_permission"


class DocumentStatus(StrEnum):
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
