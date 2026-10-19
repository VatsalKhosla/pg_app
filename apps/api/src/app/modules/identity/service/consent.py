"""Consent under the DPDP Act (ARCHITECTURE §12): given at sign-up for the required purposes, later
for optional ones, and withdrawn at any time except where the account needs it.

The privacy notice's text lives in the web app; the API knows its current version
(PRIVACY_NOTICE_VERSION), which every consent records. When the version changes, signed-in people
are asked to agree again (``consentRequired`` on /v1/me).
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.identity.domain.consent import (
    REQUIRED_PURPOSES,
    ConsentPurpose,
    is_current,
    missing_required,
)
from app.modules.identity.errors import (
    ConsentNeededForAccountError,
    ConsentRequiredError,
    PrivacyNoticeChangedError,
)
from app.modules.identity.repository import ConsentRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.clock import Clock
    from app.modules.identity.models import Consent


@dataclass(frozen=True)
class ConsentGiven:
    """What a person agreed to: the notice version they were shown, and the purposes they chose."""

    notice_version: str
    purposes: frozenset[ConsentPurpose]


@dataclass(frozen=True)
class PrivacyNotice:
    version: str
    # Every purpose, and whether the account needs it.
    purposes: tuple[tuple[ConsentPurpose, bool], ...]


def privacy_notice(version: str) -> PrivacyNotice:
    return PrivacyNotice(
        version=version,
        purposes=tuple((purpose, purpose in REQUIRED_PURPOSES) for purpose in ConsentPurpose),
    )


def check_consent(consent: ConsentGiven, *, notice_version: str, signing_up: bool) -> None:
    """Refuse consent to an old notice, and a sign-up without the required purposes."""
    if consent.notice_version != notice_version:
        raise PrivacyNoticeChangedError
    if signing_up and missing_required(consent.purposes):
        raise ConsentRequiredError


class ConsentService:
    def __init__(self, db: AsyncSession, clock: Clock, *, notice_version: str) -> None:
        self._db = db
        self._clock = clock
        self._notice_version = notice_version
        self._consents = ConsentRepository(db)

    async def history(self, user_id: int) -> list[Consent]:
        async with self._db.begin():
            return await self._consents.history(user_id)

    async def grant(self, user_id: int, consent: ConsentGiven) -> list[Consent]:
        """Record consent given while signed in (a new notice version, or an optional purpose)."""
        check_consent(consent, notice_version=self._notice_version, signing_up=False)
        async with self._db.begin():
            await self._consents.grant(
                user_id,
                consent.purposes,
                notice_version=consent.notice_version,
                now=self._clock.now(),
            )
            return await self._consents.history(user_id)

    async def withdraw(self, user_id: int, purpose: ConsentPurpose) -> None:
        """Withdraw an optional purpose; safe to repeat. A required one can't go while the
        account exists: that takes a deletion request."""
        if purpose in REQUIRED_PURPOSES:
            raise ConsentNeededForAccountError
        async with self._db.begin():
            await self._consents.withdraw(user_id, purpose, now=self._clock.now())

    async def is_current(self, user_id: int) -> bool:
        async with self._db.begin():
            active = await self._consents.active(user_id)
        return is_current(active, notice_version=self._notice_version)
