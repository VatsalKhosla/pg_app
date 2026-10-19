"""Consent under the DPDP Act (ARCHITECTURE §12): what people agree to, against which version of
the privacy notice.

Consent is given per purpose, never assumed: a purpose counts only when the person chose it (no
pre-ticked boxes, CLAUDE.md rule 7). The account can't exist without the required purposes; the
optional ones can be given and withdrawn at any time. The notice's text lives in the web app; the
API knows only its version, which every consent records.
"""

from enum import StrEnum
from typing import Final


class ConsentPurpose(StrEnum):
    # Running the account and the service: signing in, visits, bookings, payments, and the
    # messages about them.
    ACCOUNT = "account"
    # Offers and news by SMS, WhatsApp or email.
    MARKETING = "marketing"


# Without these there is no account; withdrawing them means asking for the account's deletion.
REQUIRED_PURPOSES: Final = frozenset({ConsentPurpose.ACCOUNT})


def missing_required(purposes: frozenset[ConsentPurpose]) -> frozenset[ConsentPurpose]:
    return REQUIRED_PURPOSES - purposes


def is_current(active: frozenset[tuple[ConsentPurpose, str]], *, notice_version: str) -> bool:
    """Whether the active consents (purpose and notice version) cover every required purpose
    under the current notice; if not, the person must be asked again."""
    return all((purpose, notice_version) in active for purpose in REQUIRED_PURPOSES)
