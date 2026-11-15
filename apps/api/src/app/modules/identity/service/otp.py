"""Sign-in by a code (ARCHITECTURE §12, ADR 0068): send a code to a phone or an email address,
check it, find or create the account.

Abuse controls, in the order a request meets them:
1. Per-IP limits on requests and checks (the routes).
2. A Turnstile check before any code is sent.
3. A 30-second cooldown per phone or address (in PostgreSQL, under a lock for it).
4. At most five codes per phone or address per hour (Redis, refusing if Redis is down).
5. Five wrong tries lock a code.

Responses never say whether a phone number or address has an account. Codes are HMACs under
SECRET_KEY, bound to their challenge, and never stored or logged in plain text outside
development. A code proves the phone or address it went to, so it signs in to the account with
that phone or address (an address on an account is never one typed in unproven: domain/emails.py).

A first sign-in creates the account only with consent to the current privacy notice. Without it
the answer is CONSENT_REQUIRED, given only once the code has proved to be right (so it says nothing
to anyone without the phone), and the challenge stays usable for a second try with the consent.
An account ops made for someone (an owner) counts as new until its person has agreed.
"""

import hmac
import ipaddress
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Final

import structlog
from opentelemetry import metrics

from app.core.errors import AppError, ServiceUnavailableError
from app.core.hashing import keyed_digest
from app.core.human_check import HumanCheckFailedError
from app.core.ids import new_public_id
from app.core.pii import mask_email
from app.core.ratelimit import RateLimit, enforce
from app.modules.identity.domain.consent import has_agreed
from app.modules.identity.domain.otp import (
    CODE_DIGITS,
    HUMAN_CHECK_ACTION,
    RESEND_COOLDOWN,
    ChallengeState,
    Channel,
    Destination,
    OtpPurpose,
    attempts_left,
    challenge_state,
    resend_wait,
)
from app.modules.identity.errors import (
    AccountSuspendedError,
    ConsentRequiredError,
    OtpExpiredError,
    OtpInvalidError,
    OtpLockedError,
    OtpResendTooSoonError,
)
from app.modules.identity.models import OtpChallenge
from app.modules.identity.repository import ConsentRepository, OtpRepository, UserRepository
from app.modules.identity.service.consent import check_consent

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.clock import Clock
    from app.core.human_check import HumanCheck
    from app.core.ratelimit import RateLimiter
    from app.modules.identity.models import User
    from app.modules.identity.ports import EmailCodeSender, OtpSender
    from app.modules.identity.service.consent import ConsentGiven

# At most five codes per phone per hour; refuse while Redis is down, since each code costs an SMS.
OTP_SENDS_PER_PHONE: Final = RateLimit(
    "otp-sends-per-phone", limit=5, window=timedelta(hours=1), fail_open=False
)
# The same for an address, which no one should be able to flood with mail.
OTP_SENDS_PER_EMAIL: Final = RateLimit(
    "otp-sends-per-email", limit=5, window=timedelta(hours=1), fail_open=False
)
_SENDS_PER: Final = {Channel.PHONE: OTP_SENDS_PER_PHONE, Channel.EMAIL: OTP_SENDS_PER_EMAIL}
# Challenges (with the phone number or address, IP address and user agent) are deleted after this
# long.
OTP_RETENTION: Final = timedelta(days=7)
_MAX_USER_AGENT_LENGTH: Final = 512

logger = structlog.stdlib.get_logger(__name__)
_meter = metrics.get_meter("app.identity")
# Counted by outcome, so spikes of failures or sends can raise alerts (ARCHITECTURE §17).
_codes_sent = _meter.create_counter("identity.otp.sent", unit="{code}")
_checks = _meter.create_counter("identity.otp.checks", unit="{check}")


@dataclass(frozen=True)
class IssuedChallenge:
    public_id: uuid.UUID
    expires_at: datetime
    resend_after: datetime
    # The code itself, only from a sender that shows it (local development's console sender, and a
    # test site's screen sender).
    development_code: str | None = None


@dataclass(frozen=True)
class SignedIn:
    user_id: int
    new_user: bool


def _logged(destination: Destination) -> dict[str, str]:
    """How a destination appears in the log: phones are masked by the log itself (core/logging),
    addresses here."""
    if destination.channel is Channel.PHONE:
        return {"phone": destination.address}
    return {"email": mask_email(destination.address)}


def _clean_ip(value: str | None) -> str | None:
    try:
        return None if value is None else str(ipaddress.ip_address(value))
    except ValueError:
        return None


class OtpService:
    def __init__(
        self,
        db: AsyncSession,
        clock: Clock,
        *,
        secret: bytes,
        sender: OtpSender,
        email_codes: EmailCodeSender,
        human_check: HumanCheck,
        limiter: RateLimiter,
        notice_version: str,
        phone_sign_in: bool = True,
    ) -> None:
        self._db = db
        self._clock = clock
        self._secret = secret
        self._sender = sender
        self._email_codes = email_codes
        self._human_check = human_check
        self._limiter = limiter
        self._notice_version = notice_version
        self._phone_sign_in = phone_sign_in
        self._challenges = OtpRepository(db)
        self._users = UserRepository(db)
        self._consents = ConsentRepository(db)

    @property
    def phone_available(self) -> bool:
        """Codes by text: off until the text sender is registered (PHONE_SIGN_IN=false, or no
        sender at all)."""
        return self._phone_sign_in

    @property
    def email_available(self) -> bool:
        return self._email_codes.available

    def _code_hash(self, challenge: uuid.UUID, code: str) -> str:
        return keyed_digest(self._secret, purpose="otp", value=f"{challenge}:{code}")

    async def request(
        self,
        phone_e164: str,
        *,
        human_check_token: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> IssuedChallenge:
        """Send a new sign-in code to ``phone_e164`` by text, replacing any earlier one."""
        if not self._phone_sign_in:
            raise ServiceUnavailableError("Signing in by phone isn't available yet.")
        return await self._issue(
            Destination(Channel.PHONE, phone_e164),
            human_check_token=human_check_token,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def request_email(
        self,
        email: str,
        *,
        human_check_token: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> IssuedChallenge:
        """Send a new sign-in code to ``email`` (lowercase), replacing any earlier one."""
        if not self._email_codes.available:
            raise ServiceUnavailableError("Signing in by email isn't available yet.")
        return await self._issue(
            Destination(Channel.EMAIL, email),
            human_check_token=human_check_token,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def _issue(
        self,
        destination: Destination,
        *,
        human_check_token: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> IssuedChallenge:
        ip_address = _clean_ip(ip_address)
        if not await self._human_check.verify(
            human_check_token, remote_ip=ip_address, action=HUMAN_CHECK_ACTION
        ):
            raise HumanCheckFailedError
        purpose = OtpPurpose.SIGN_IN
        code = f"{secrets.randbelow(10**CODE_DIGITS):0{CODE_DIGITS}d}"
        now = self._clock.now()
        by_phone = destination.channel is Channel.PHONE
        async with self._db.begin():
            await self._challenges.lock(destination)
            wait = resend_wait(
                now=now,
                last_requested_at=await self._challenges.last_requested_at(
                    destination, purpose=purpose
                ),
            )
            if wait > timedelta(0):
                raise OtpResendTooSoonError(wait)
            await enforce(self._limiter, _SENDS_PER[destination.channel], destination.address)
            await self._challenges.supersede_open(destination, purpose=purpose, now=now)
            public_id = new_public_id()
            challenge = OtpChallenge(
                public_id=public_id,
                phone_e164=destination.address if by_phone else None,
                email=None if by_phone else destination.address,
                purpose=purpose,
                code_hash=self._code_hash(public_id, code),
                attempts=0,
                requested_at=now,
                expires_at=now + destination.code_ttl,
                ip_address=ip_address,
                user_agent=None if user_agent is None else user_agent[:_MAX_USER_AGENT_LENGTH],
            )
            self._challenges.add(challenge)
            await self._db.flush()
        channel = {"channel": destination.channel.value}
        try:
            if by_phone:
                await self._sender.send(destination.address, code)
            else:
                await self._email_codes.send(destination.address, code)
        except Exception as error:
            logger.exception("sign-in code not sent", **_logged(destination))
            _codes_sent.add(1, {"outcome": "failed", **channel})
            # Undo the challenge, so the cooldown doesn't hold up an immediate retry.
            async with self._db.begin():
                await self._challenges.delete(challenge.id)
            if isinstance(error, AppError):
                raise
            raise ServiceUnavailableError("We couldn't send the code. Please try again.") from None
        _codes_sent.add(1, {"outcome": "sent", **channel})
        logger.info("sign-in code sent", **_logged(destination))
        shown = self._sender.shows_code if by_phone else self._email_codes.shows_code
        return IssuedChallenge(
            public_id=challenge.public_id,
            expires_at=challenge.expires_at,
            resend_after=now + RESEND_COOLDOWN,
            development_code=code if shown else None,
        )

    async def verify(
        self, challenge_id: uuid.UUID, code: str, *, consent: ConsentGiven | None = None
    ) -> SignedIn:
        """Check ``code`` against the challenge and sign in the owner of the phone or address it
        went to, recording ``consent`` if given; a new account needs it."""
        now = self._clock.now()
        async with self._db.begin():
            challenge = await self._challenges.by_public_id_for_update(challenge_id)
            outcome = await self._use(challenge, code, now, consent)
        # Committed by now: a wrong code counts as an attempt even though it is refused.
        if isinstance(outcome, OtpInvalidError):
            raise _refused("wrong_code", outcome)
        user, created = outcome
        if user.status != "active":
            raise _refused("suspended", AccountSuspendedError())
        _checks.add(1, {"outcome": "signed_in"})
        logger.info("signed in with a code", user_id=user.id, new_user=created)
        return SignedIn(user_id=user.id, new_user=created)

    async def _use(
        self,
        challenge: OtpChallenge | None,
        code: str,
        now: datetime,
        consent: ConsentGiven | None,
    ) -> tuple[User, bool] | OtpInvalidError:
        """Within the verify transaction: refuse an unusable challenge (nothing changes), count a
        wrong code, or consume a right one and find or create the account."""
        if challenge is None:
            raise _refused("unknown", OtpInvalidError())
        state = challenge_state(
            now=now,
            expires_at=challenge.expires_at,
            attempts=challenge.attempts,
            consumed_at=challenge.consumed_at,
            superseded_at=challenge.superseded_at,
        )
        if state is not ChallengeState.OPEN:
            raise _refused(state, _UNUSABLE[state]())
        expected = self._code_hash(challenge.public_id, code)
        if not hmac.compare_digest(challenge.code_hash.encode(), expected.encode()):
            challenge.attempts += 1
            left = attempts_left(challenge.attempts)
            detail = f"{left} attempts left." if left else "No attempts left; ask for a new code."
            return OtpInvalidError(detail)
        phone, email = challenge.phone_e164, challenge.email
        existing = await (
            self._users.by_phone(phone) if phone is not None else self._users.by_email(email or "")
        )
        # A first sign-in: no account yet, or one made for this person that they never agreed to.
        first = existing is None or not has_agreed(await self._consents.active(existing.id))
        if consent is not None:
            check_consent(consent, notice_version=self._notice_version, signing_up=first)
        elif first:
            # Nothing has changed yet, so the challenge stays open for a try with the consent.
            raise _refused("consent_required", ConsentRequiredError())
        challenge.consumed_at = now
        user, created = await (
            self._users.get_or_create_by_phone(phone)
            if phone is not None
            else self._users.get_or_create_by_email(email or "")
        )
        if consent is not None:
            await self._consents.grant(
                user.id, consent.purposes, notice_version=consent.notice_version, now=now
            )
        return user, created


# What an unusable challenge answers. A used or replaced code is "invalid", like a wrong one.
_UNUSABLE: Final[dict[ChallengeState, type[AppError]]] = {
    ChallengeState.USED: OtpInvalidError,
    ChallengeState.LOCKED: OtpLockedError,
    ChallengeState.EXPIRED: OtpExpiredError,
}


def _refused(reason: str, error: AppError) -> AppError:
    """Count a refused check by reason (for alerts on spikes) and hand back the error to raise."""
    _checks.add(1, {"outcome": reason})
    return error


async def delete_old_challenges(db: AsyncSession, clock: Clock) -> int:
    """Retention: drop sign-in challenges older than OTP_RETENTION."""
    return await OtpRepository(db).delete_requested_before(clock.now() - OTP_RETENTION)
