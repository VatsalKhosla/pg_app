"""Staff sign-in and staff accounts (ARCHITECTURE §12).

Staff sign in with Google, if their Google account is allowed, or with a phone code followed by a
code from an authenticator app, until the company has a Google Workspace domain. Either way they
get a staff session: 12 hours from sign-in, and the only kind that carries staff roles. Being
allowed by Google isn't enough: an admin must have made the user staff (python -m app.manage).
Every refusal looks the same from outside (STAFF_ACCOUNT_NOT_ALLOWED), and is logged with its
reason.

A Google sign-in keeps no server state. A random login id goes into a short-lived host-only cookie,
and the state, nonce and PKCE verifier are HMACs of it under SECRET_KEY: only the browser that
started a sign-in can finish it, and nothing about one sign-in helps with another.
"""

import base64
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Final

import structlog
from opentelemetry import metrics

from app.config import BRAND_NAME
from app.core import audit
from app.core.actor import STAFF_ROLES, Role
from app.core.errors import AppError, ServiceUnavailableError
from app.core.pagination import split_page
from app.core.ratelimit import RateLimit, enforce
from app.modules.identity.domain.staff import IdentityProvider, google_account_allowed
from app.modules.identity.domain.totp import (
    SALT_BYTES,
    SECRET_BYTES,
    matching_step,
    provisioning_uri,
    secret_text,
)
from app.modules.identity.errors import (
    StaffAccountNotAllowedError,
    StaffSignInCancelledError,
    StaffSignInExpiredError,
    TotpInvalidError,
)
from app.modules.identity.models import UserIdentity
from app.modules.identity.repository import (
    IdentityRepository,
    StaffRecord,
    TotpRepository,
    UserRepository,
)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.core.pagination import PageRequest
    from app.core.ratelimit import RateLimiter
    from app.modules.identity.domain.staff import GoogleAccount
    from app.modules.identity.models import User
    from app.modules.identity.ports import GoogleSignIn

# A Google sign-in must be finished within this long of starting it.
LOGIN_TTL: Final = timedelta(minutes=10)
# Authenticator codes: five tries per staff member per 15 minutes, refused while Redis is down.
TOTP_CHECKS_PER_USER: Final = RateLimit(
    "staff-totp-checks-per-user", limit=5, window=timedelta(minutes=15), fail_open=False
)
# The name authenticator apps show next to the codes.
AUTHENTICATOR_ISSUER: Final = f"{BRAND_NAME} staff"
_LOGIN_ID: Final = re.compile(r"(?P<nonce>[A-Za-z0-9_-]{43})\.(?P<issued>[0-9]{1,12})")
_CLOCK_SKEW: Final = timedelta(minutes=1)

logger = structlog.stdlib.get_logger(__name__)
# Counted by method and outcome, so refusals and failures can raise alerts (ARCHITECTURE §17).
_sign_ins = metrics.get_meter("app.identity").create_counter(
    "identity.staff.sign_ins", unit="{sign_in}"
)


@dataclass(frozen=True)
class GoogleLogin:
    """A Google sign-in to start: the login cookie's value, and where to send the browser."""

    cookie: str
    authorization_url: str


@dataclass(frozen=True)
class Enrolment:
    """A new authenticator app: the link to scan and the secret to type in. Shown once."""

    uri: str
    secret: str


class StaffAdminError(Exception):
    """An operator command that can't be carried out; the message says why."""


@dataclass(frozen=True)
class _LoginSecrets:
    state: str
    nonce: str
    code_verifier: str

    @property
    def code_challenge(self) -> str:
        return _b64(hashlib.sha256(self.code_verifier.encode()).digest())


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _derive(secret: bytes, purpose: str, value: str) -> str:
    return _b64(hmac.new(secret, f"{purpose}\x00{value}".encode(), hashlib.sha256).digest())


def _login_secrets(secret: bytes, login_id: str) -> _LoginSecrets:
    # 43 characters each: a valid PKCE verifier (RFC 7636 asks for 43 to 128).
    return _LoginSecrets(
        state=_derive(secret, "staff-login-state", login_id),
        nonce=_derive(secret, "staff-login-nonce", login_id),
        code_verifier=_derive(secret, "staff-login-pkce", login_id),
    )


def totp_secret(secret: bytes, salt: bytes) -> bytes:
    """An authenticator's secret, derived again whenever a code is checked: the database keeps only
    the salt, so a copy of it holds no secret. Rotating SECRET_KEY means enrolling again."""
    message = b"totp\x00" + salt
    return hmac.new(secret, message, hashlib.sha256).digest()[:SECRET_BYTES]


def _refused(reason: str, *, method: str, **context: object) -> AppError:
    logger.info("staff sign-in refused", reason=reason, method=method, **context)
    _sign_ins.add(1, {"method": method, "outcome": reason})
    return StaffAccountNotAllowedError()


class StaffSignInService:
    def __init__(
        self,
        db: AsyncSession,
        clock: Clock,
        *,
        secret: bytes,
        google: GoogleSignIn | None,
        google_domains: frozenset[str],
        google_emails: frozenset[str],
        limiter: RateLimiter,
    ) -> None:
        self._db = db
        self._clock = clock
        self._secret = secret
        self._google = google
        self._google_domains = google_domains
        self._google_emails = google_emails
        self._limiter = limiter
        self._users = UserRepository(db)
        self._identities = IdentityRepository(db)
        self._totp = TotpRepository(db)

    def _require_google(self) -> GoogleSignIn:
        if self._google is None:
            raise ServiceUnavailableError("Signing in with Google isn't set up.")
        return self._google

    def start_google(self) -> GoogleLogin:
        """A new Google sign-in for this browser."""
        google = self._require_google()
        login_id = f"{secrets.token_urlsafe(32)}.{int(self._clock.now().timestamp())}"
        derived = _login_secrets(self._secret, login_id)
        url = google.authorization_url(
            state=derived.state, nonce=derived.nonce, code_challenge=derived.code_challenge
        )
        return GoogleLogin(cookie=login_id, authorization_url=url)

    async def finish_google(
        self, *, login_cookie: str | None, state: str | None, code: str | None, error: str | None
    ) -> int:
        """Finish the Google sign-in Google redirected back from; returns the staff user's id."""
        google = self._require_google()
        if error is not None:
            if error == "access_denied":
                raise StaffSignInCancelledError
            logger.error("Google sign-in failed at Google", oauth_error=error[:64])
            raise ServiceUnavailableError("Signing in with Google isn't working right now.")
        derived = self._login(login_cookie)
        if state is None or code is None or not hmac.compare_digest(state, derived.state):
            raise StaffSignInExpiredError
        account = await google.finish(
            code, code_verifier=derived.code_verifier, nonce=derived.nonce
        )
        if not google_account_allowed(
            account, domains=self._google_domains, emails=self._google_emails
        ):
            raise _refused(
                "account_not_allowed", method="google", hosted_domain=account.hosted_domain
            )
        async with self._db.begin():
            user = await self._google_user(account)
            if user is None:
                raise _refused("not_staff", method="google")
            await self._record_sign_in(user, method="google")
        return user.id

    def _login(self, login_cookie: str | None) -> _LoginSecrets:
        """The secrets of the sign-in this browser started, if it started one recently."""
        match = _LOGIN_ID.fullmatch(login_cookie or "")
        if login_cookie is None or match is None:
            raise StaffSignInExpiredError
        age = self._clock.now().timestamp() - int(match["issued"])
        if not -_CLOCK_SKEW.total_seconds() <= age <= LOGIN_TTL.total_seconds():
            raise StaffSignInExpiredError
        return _login_secrets(self._secret, login_cookie)

    async def _google_user(self, account: GoogleAccount) -> User | None:
        """The active staff user a Google account signs in as, if any: the user it is linked to
        or, the first time, the user with its address, which it is then linked to (unless that
        user is linked to a different Google account, as when an address changes hands)."""
        now = self._clock.now()
        identity = await self._identities.find(IdentityProvider.GOOGLE, account.subject)
        if identity is not None:
            user = await self._users.get(identity.user_id)
            if user is None or not await self._is_active_staff(user):
                return None
            identity.last_used_at = now
            return user
        user = await self._users.by_email(account.email)
        if user is None or not await self._is_active_staff(user):
            return None
        if await self._identities.for_user(user.id, IdentityProvider.GOOGLE) is not None:
            logger.warning("address linked to a different Google account", user_id=user.id)
            return None
        self._identities.add(
            UserIdentity(
                user_id=user.id,
                provider=IdentityProvider.GOOGLE,
                subject=account.subject,
                email=account.email,
                last_used_at=now,
            )
        )
        await audit.record(
            self._db,
            clock=self._clock,
            actor=audit.Actor("staff", user.id),
            action="staff.google_linked",
            entity_type="user",
            entity_id=str(user.public_id),
        )
        return user

    async def verify_totp(self, actor: Actor, code: str) -> int:
        """Step up from a phone sign-in with an authenticator code; returns the staff user's
        id. Each code works once, and a staff member gets five tries per 15 minutes."""
        await enforce(self._limiter, TOTP_CHECKS_PER_USER, str(actor.user_id))
        async with self._db.begin():
            user = await self._users.get(actor.user_id)
            credential = await self._totp.for_user(actor.user_id, for_update=True)
            if (
                user is None
                or not await self._is_active_staff(user)
                or credential is None
                or credential.confirmed_at is None
            ):
                raise _refused("no_authenticator", method="authenticator")
            step = matching_step(
                totp_secret(self._secret, credential.salt),
                code,
                now=self._clock.now(),
                last_used_step=credential.last_used_step,
            )
            if step is None:
                _sign_ins.add(1, {"method": "authenticator", "outcome": "wrong_code"})
                raise TotpInvalidError
            credential.last_used_step = step
            await self._record_sign_in(user, method="authenticator")
        return user.id

    async def _is_active_staff(self, user: User) -> bool:
        if user.status != "active":
            return False
        return not (await self._users.roles(user.id)).isdisjoint(STAFF_ROLES)

    async def _record_sign_in(self, user: User, *, method: str) -> None:
        await audit.record(
            self._db,
            clock=self._clock,
            actor=audit.Actor("staff", user.id),
            action="staff.sign_in",
            entity_type="user",
            entity_id=str(user.public_id),
            details={"method": method},
        )
        _sign_ins.add(1, {"method": method, "outcome": "signed_in"})
        logger.info("staff signed in", user_id=user.id, method=method)


class StaffDirectory:
    """Who is staff, for admins."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._users = UserRepository(db)

    async def page(self, request: PageRequest) -> tuple[list[StaffRecord], uuid.UUID | None]:
        async with self._db.begin():
            rows = await self._users.staff_page(after=request.after, limit=request.limit)
        return split_page(rows, request, cursor_of=lambda row: row.user.public_id)


class StaffAdmin:
    """The operator commands behind ``python -m app.manage staff``, audited as the system."""

    def __init__(self, db: AsyncSession, clock: Clock, *, secret: bytes) -> None:
        self._db = db
        self._clock = clock
        self._secret = secret
        self._users = UserRepository(db)
        self._identities = IdentityRepository(db)
        self._totp = TotpRepository(db)

    async def add(
        self, phone_e164: str, roles: frozenset[Role], *, email: str | None, name: str | None
    ) -> frozenset[Role]:
        """Give the account for ``phone_e164`` (created if there is none) the staff ``roles``,
        and set its address and name if given. Returns its staff roles."""
        if not roles or not roles <= STAFF_ROLES:
            msg = "give one or more staff roles"
            raise StaffAdminError(msg)
        async with self._db.begin():
            user, _ = await self._users.get_or_create_by_phone(phone_e164)
            if email is not None:
                owner = await self._users.by_email(email)
                if owner is not None and owner.id != user.id:
                    msg = "that address belongs to another account"
                    raise StaffAdminError(msg)
                user.email = email
            if name is not None:
                user.name = name
            await self._users.add_roles(user.id, roles)
            await self._audit(user, "staff.roles_granted", {"roles": sorted(roles)})
            return await self._users.roles(user.id) & STAFF_ROLES

    async def remove(self, phone_e164: str, roles: frozenset[Role] | None) -> frozenset[Role]:
        """Take staff ``roles`` (all of them when None) from the account. Without any staff role
        its staff sessions stop working, and its authenticator app is removed. Returns the staff
        roles left."""
        async with self._db.begin():
            user = await self._staff_user(phone_e164)
            current = await self._users.roles(user.id) & STAFF_ROLES
            removed = current & (STAFF_ROLES if roles is None else roles)
            await self._users.remove_roles(user.id, removed)
            remaining = current - removed
            if not remaining:
                await self._totp.delete_for_user(user.id)
            await self._audit(user, "staff.roles_removed", {"roles": sorted(removed)})
            return remaining

    async def enrol_authenticator(self, phone_e164: str) -> Enrolment:
        """A new authenticator app for a staff member, replacing any earlier one. It can't sign
        in until confirmed with its first code."""
        async with self._db.begin():
            user = await self._staff_user(phone_e164)
            salt = secrets.token_bytes(SALT_BYTES)
            await self._totp.replace(user.id, salt=salt)
            secret = totp_secret(self._secret, salt)
            account = user.email or user.phone_e164
        return Enrolment(
            uri=provisioning_uri(secret, issuer=AUTHENTICATOR_ISSUER, account=account),
            secret=secret_text(secret),
        )

    async def confirm_authenticator(self, phone_e164: str, code: str) -> bool:
        """Confirm the authenticator app with a code from it; False if the code is wrong."""
        async with self._db.begin():
            user = await self._staff_user(phone_e164)
            credential = await self._totp.for_user(user.id, for_update=True)
            if credential is None:
                msg = "no authenticator app is being set up for that account"
                raise StaffAdminError(msg)
            step = matching_step(
                totp_secret(self._secret, credential.salt),
                code,
                now=self._clock.now(),
                last_used_step=credential.last_used_step,
            )
            if step is None:
                return False
            credential.confirmed_at = self._clock.now()
            credential.last_used_step = step
            await self._audit(user, "staff.authenticator_enrolled", {})
            return True

    async def remove_authenticator(self, phone_e164: str) -> bool:
        async with self._db.begin():
            user = await self._user(phone_e164)
            removed = await self._totp.delete_for_user(user.id)
            if removed:
                await self._audit(user, "staff.authenticator_removed", {})
            return removed

    async def remove_google(self, phone_e164: str) -> bool:
        """Unlink the account's Google account, so that its next Google sign-in links again: for
        someone whose Google account was replaced (Google never reuses an account's id)."""
        async with self._db.begin():
            user = await self._user(phone_e164)
            removed = await self._identities.delete_for_user(user.id, IdentityProvider.GOOGLE)
            if removed:
                await self._audit(user, "staff.google_unlinked", {})
            return removed

    async def _user(self, phone_e164: str) -> User:
        user = await self._users.by_phone(phone_e164)
        if user is None:
            msg = "no account has that phone number"
            raise StaffAdminError(msg)
        return user

    async def _staff_user(self, phone_e164: str) -> User:
        user = await self._user(phone_e164)
        if (await self._users.roles(user.id)).isdisjoint(STAFF_ROLES):
            msg = "that account isn't staff"
            raise StaffAdminError(msg)
        return user

    async def _audit(self, user: User, action: str, details: dict[str, object]) -> None:
        await audit.record(
            self._db,
            clock=self._clock,
            actor=audit.SYSTEM,
            action=action,
            entity_type="user",
            entity_id=str(user.public_id),
            details={**details, "via": "cli"},
        )
