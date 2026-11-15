"""Signing in with Google, for anyone (ADR 0068): students, parents and owners.

Google proves the account's address (only a verified one is used), so the sign-in is to the
account with that address, made on a first sign-in, as an email code would be. The Google account
is linked to it on first use; after that, its id finds the account even if the address changes.
An account with that address that is already linked to a different Google account (an address
that changed hands) isn't signed in to.

Consent works as with codes: a first sign-in needs it. The person ticks it before leaving for
Google, so it travels in the login (service/google_login.py); a first sign-in without it comes
back asking for it, and nothing is made.

Staff sign-in (service/staff.py) shares the Google client, its callback and the login mechanics,
but stays separate: only it gives staff sessions.
"""

import base64
import binascii
import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import structlog
from opentelemetry import metrics
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core import audit
from app.core.errors import ServiceUnavailableError
from app.modules.identity.domain.consent import ConsentPurpose, has_agreed
from app.modules.identity.domain.emails import normalize_email
from app.modules.identity.domain.return_paths import safe_return_path
from app.modules.identity.domain.staff import IdentityProvider
from app.modules.identity.errors import (
    AccountSuspendedError,
    ConsentRequiredError,
    GoogleAccountNotUsableError,
    GoogleSignInCancelledError,
    GoogleSignInExpiredError,
    StaffSignInExpiredError,
)
from app.modules.identity.models import UserIdentity
from app.modules.identity.repository import ConsentRepository, IdentityRepository, UserRepository
from app.modules.identity.service.consent import ConsentGiven, check_consent
from app.modules.identity.service.google_login import (
    GoogleLogin,
    login_is_fresh,
    login_secrets,
    new_login_id,
    same_state,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.clock import Clock
    from app.modules.identity.domain.staff import GoogleAccount
    from app.modules.identity.models import User
    from app.modules.identity.ports import GoogleSignIn

_KIND: Final = "people"
_LOGIN_ID: Final = re.compile(
    r"(?P<nonce>[A-Za-z0-9_-]{43})\.(?P<issued>[0-9]{1,12})\.(?P<carried>[A-Za-z0-9_-]{1,1200})"
)

logger = structlog.stdlib.get_logger(__name__)
_sign_ins = metrics.get_meter("app.identity").create_counter(
    "identity.google.sign_ins", unit="{sign_in}"
)


class _Carried(BaseModel):
    """What a sign-in carries to its end, in its login id: the consent given and the page to go
    back to."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    notice: str | None = Field(default=None, max_length=64)
    purposes: tuple[ConsentPurpose, ...] = Field(default=(), max_length=len(ConsentPurpose))
    back: str | None = Field(default=None, max_length=512)

    def encoded(self) -> str:
        raw = self.model_dump_json(exclude_defaults=True).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    @classmethod
    def decoded(cls, value: str) -> _Carried | None:
        try:
            raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
            return cls.model_validate(json.loads(raw))
        except binascii.Error, ValueError, ValidationError:
            return None

    @property
    def consent(self) -> ConsentGiven | None:
        if self.notice is None:
            return None
        return ConsentGiven(notice_version=self.notice, purposes=frozenset(self.purposes))


@dataclass(frozen=True)
class GoogleSignedIn:
    user_id: int
    new_user: bool
    # The page the person was on, to go back to.
    back: str | None


def _refused(reason: str, error: Exception) -> Exception:
    _sign_ins.add(1, {"outcome": reason})
    logger.info("Google sign-in refused", reason=reason)
    return error


class GoogleSignInService:
    def __init__(
        self,
        db: AsyncSession,
        clock: Clock,
        *,
        secret: bytes,
        google: GoogleSignIn | None,
        notice_version: str,
    ) -> None:
        self._db = db
        self._clock = clock
        self._secret = secret
        self._google = google
        self._notice_version = notice_version
        self._users = UserRepository(db)
        self._identities = IdentityRepository(db)
        self._consents = ConsentRepository(db)

    @property
    def available(self) -> bool:
        return self._google is not None

    def _require_google(self) -> GoogleSignIn:
        if self._google is None:
            raise ServiceUnavailableError("Signing in with Google isn't set up.")
        return self._google

    def start(self, *, consent: ConsentGiven | None, back: str | None) -> GoogleLogin:
        """A new Google sign-in for this browser, carrying ``consent`` (for a first sign-in) and
        the page to go back to (a path on the site; anything else is dropped)."""
        google = self._require_google()
        carried = _Carried(
            notice=None if consent is None else consent.notice_version,
            purposes=() if consent is None else tuple(sorted(consent.purposes)),
            back=safe_return_path(back),
        )
        login_id = new_login_id(self._clock.now(), carried.encoded())
        derived = login_secrets(self._secret, login_id, kind=_KIND)
        url = google.authorization_url(
            state=derived.state,
            nonce=derived.nonce,
            code_challenge=derived.code_challenge,
            any_account=True,
        )
        return GoogleLogin(cookie=login_id, authorization_url=url)

    def started_here(self, login_cookie: str | None, state: str | None) -> bool:
        """Whether Google is sending back a sign-in this browser started here (not a staff one,
        which shares the callback)."""
        if login_cookie is None or _LOGIN_ID.fullmatch(login_cookie) is None:
            return False
        return same_state(login_secrets(self._secret, login_cookie, kind=_KIND).state, state)

    @staticmethod
    def back(login_cookie: str | None) -> str | None:
        """The page a sign-in started from, to send the person back to after a refusal."""
        match = _LOGIN_ID.fullmatch(login_cookie or "")
        carried = None if match is None else _Carried.decoded(match["carried"])
        return None if carried is None else safe_return_path(carried.back)

    async def finish(
        self, *, login_cookie: str | None, state: str | None, code: str | None, error: str | None
    ) -> GoogleSignedIn:
        """Finish the sign-in Google sent back: the account with the Google account's address,
        made on a first sign-in (which needs the consent the login carries)."""
        google = self._require_google()
        if error is not None:
            if error == "access_denied":
                raise _refused("cancelled", GoogleSignInCancelledError())
            logger.error("Google sign-in failed at Google", oauth_error=error[:64])
            raise ServiceUnavailableError("Signing in with Google isn't working right now.")
        login_id, carried = self._login(login_cookie)
        derived = login_secrets(self._secret, login_id, kind=_KIND)
        if code is None or not same_state(derived.state, state):
            raise _refused("expired", GoogleSignInExpiredError())
        try:
            account = await google.finish(
                code, code_verifier=derived.code_verifier, nonce=derived.nonce
            )
        except StaffSignInExpiredError:
            raise _refused("expired", GoogleSignInExpiredError()) from None
        email = normalize_email(account.email) if account.email_verified else None
        if email is None:
            raise _refused("unverified_email", GoogleAccountNotUsableError())
        async with self._db.begin():
            user, created = await self._account(account, email, carried.consent)
        if user.status != "active":
            raise _refused("suspended", AccountSuspendedError())
        _sign_ins.add(1, {"outcome": "signed_in"})
        logger.info("signed in with Google", user_id=user.id, new_user=created)
        return GoogleSignedIn(user_id=user.id, new_user=created, back=carried.back)

    def _login(self, login_cookie: str | None) -> tuple[str, _Carried]:
        """The login id of the sign-in this browser started, if it started one recently, and what
        it carries."""
        match = _LOGIN_ID.fullmatch(login_cookie or "")
        if login_cookie is None or match is None:
            raise _refused("expired", GoogleSignInExpiredError())
        carried = _Carried.decoded(match["carried"])
        if carried is None or not login_is_fresh(int(match["issued"]), self._clock.now()):
            raise _refused("expired", GoogleSignInExpiredError())
        return login_cookie, carried

    async def _account(
        self, account: GoogleAccount, email: str, consent: ConsentGiven | None
    ) -> tuple[User, bool]:
        """Within the transaction: the account the Google account signs in to, made or linked as
        needed, with ``consent`` recorded. Nothing is written before every check passes."""
        now = self._clock.now()
        identity = await self._identities.find(IdentityProvider.GOOGLE, account.subject)
        user = None if identity is None else await self._users.get(identity.user_id)
        if identity is None:
            user = await self._users.by_email(email)
            if (
                user is not None
                and await self._identities.for_user(user.id, IdentityProvider.GOOGLE) is not None
            ):
                logger.warning("address linked to a different Google account", user_id=user.id)
                raise _refused("linked_elsewhere", GoogleAccountNotUsableError())
        first = user is None or not has_agreed(await self._consents.active(user.id))
        if consent is not None:
            check_consent(consent, notice_version=self._notice_version, signing_up=first)
        elif first:
            raise _refused("consent_required", ConsentRequiredError())
        created = False
        if user is None:
            user, created = await self._users.get_or_create_by_email(email)
        if identity is None:
            self._identities.add(
                UserIdentity(
                    user_id=user.id,
                    provider=IdentityProvider.GOOGLE,
                    subject=account.subject,
                    email=email,
                    last_used_at=now,
                )
            )
            await audit.record(
                self._db,
                clock=self._clock,
                actor=audit.Actor("user", user.id),
                action="user.google_linked",
                entity_type="user",
                entity_id=str(user.public_id),
            )
        else:
            identity.last_used_at = now
        if consent is not None:
            await self._consents.grant(
                user.id, consent.purposes, notice_version=consent.notice_version, now=now
            )
        return user, created
