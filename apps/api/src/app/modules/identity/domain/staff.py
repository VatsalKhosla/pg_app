"""Who may sign in to staff tools with Google (ARCHITECTURE §12).

Two gates, both required: the Google account must be allowed (an account of an allowed Google
Workspace domain, or an allowed address), and it must belong to a user an admin has made staff.
The domain comes from the ID token's ``hd`` claim, which Google sets only for accounts the
organisation manages, never from the address: anyone can own a Google account whose address
ends in a company's domain.
"""

from dataclasses import dataclass
from enum import StrEnum


class IdentityProvider(StrEnum):
    GOOGLE = "google"


@dataclass(frozen=True)
class GoogleAccount:
    """A Google account whose ID token passed every check."""

    # Google's id for the account: unique, never reused. Addresses can change hands.
    subject: str
    email: str
    email_verified: bool
    # The Google Workspace domain that manages the account; None for a personal account.
    hosted_domain: str | None


def google_account_allowed(
    account: GoogleAccount, *, domains: frozenset[str], emails: frozenset[str]
) -> bool:
    """Whether ``account`` may sign in at all. ``domains`` and ``emails`` are lowercase."""
    if not account.email_verified:
        return False
    if account.hosted_domain is not None and account.hosted_domain.lower() in domains:
        return True
    return account.email.lower() in emails
