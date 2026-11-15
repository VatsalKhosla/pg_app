"""Signing a rent agreement (ADR 0070): each side asks for a one-time code, then signs with it and
their full name typed, against the exact text they read.

Abuse controls, as signing codes meet them:
1. A 30-second wait before the same person asks again for the same agreement (in PostgreSQL,
   under the agreement's row lock).
2. At most five codes per person an hour (Redis, refusing while Redis is down: each code is an
   email), and a per-person limit on signing attempts (the routes).
3. Five wrong tries lock a code; a code lasts ten minutes and signs once, for the side that asked.

Codes are HMACs under SECRET_KEY bound to their row, never stored or logged in plain text outside
development; they go out straight away through the module's ``SigningCodeSender`` port, never
through the outbox, which would store them.

A signature is refused unless it names the agreement's text as it is now: one that changed since
the signer read it answers 409 AGREEMENT_TEXT_CHANGED, with nothing used up. A signature is then a
row the database never lets change, with the signer, their side, the typed name, the server's
time, the IP address and user agent of the request, the text's SHA-256 and the template version;
and the audit log has it too.
"""

import hmac
import ipaddress
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Final

import structlog
from opentelemetry import metrics

from app.core import audit
from app.core.errors import AppError, InvalidTransitionError, NotFoundError, ServiceUnavailableError
from app.core.hashing import keyed_digest
from app.core.ids import new_public_id
from app.core.ratelimit import RateLimit, enforce
from app.modules.agreements.domain.agreements import (
    SIGNS,
    AgreementRefusedError,
    AgreementStatus,
    Signer,
    awaits,
    transition,
)
from app.modules.agreements.domain.codes import (
    CODE_DIGITS,
    CODE_TTL,
    RESEND_COOLDOWN,
    CodeState,
    attempts_left,
    code_state,
    resend_wait,
)
from app.modules.agreements.errors import (
    AgreementNotReadyError,
    AgreementTextChangedError,
    SigningCodeExpiredError,
    SigningCodeInvalidError,
    SigningCodeLockedError,
    SigningCodeTooSoonError,
)
from app.modules.agreements.models import AgreementSignature, SigningCode
from app.modules.agreements.repository import AgreementRepository
from app.modules.agreements.service.agreements import ENTITY, RentAgreements, party_view

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.core.ratelimit import RateLimiter
    from app.modules.agreements.ports import SigningCodeSender
    from app.modules.agreements.schemas import RentAgreement
    from app.modules.agreements.service.agreements import Current
    from app.modules.agreements.templates import Templates

# At most five codes per person an hour; refused while Redis is down, as each code is an email.
SIGNING_CODES_PER_USER: Final = RateLimit(
    "signing-codes-per-user", limit=5, window=timedelta(hours=1), fail_open=False
)
# Signing codes, with the IP address and user agent that asked, are deleted after this long.
SIGNING_CODE_RETENTION: Final = timedelta(days=7)
USER_AGENT_MAX_LENGTH: Final = 512
_AUDIT_ACTORS: Final[dict[Signer, audit.ActorType]] = {
    Signer.STUDENT: "user",
    Signer.OWNER: "owner",
}

logger = structlog.stdlib.get_logger(__name__)
_meter = metrics.get_meter("app.agreements")
_codes_sent = _meter.create_counter("agreements.signing_codes.sent", unit="{code}")
_signatures = _meter.create_counter("agreements.signatures", unit="{signature}")
# Refused signings by reason, so a spike of wrong codes can raise an alert (ARCHITECTURE §17).
_refusals = _meter.create_counter("agreements.signing.refused", unit="{signing}")


@dataclass(frozen=True, slots=True)
class IssuedCode:
    expires_at: datetime
    resend_after: datetime
    # Only where nothing really sends it: local development.
    development_code: str | None


@dataclass(frozen=True, slots=True)
class Signing:
    """A signature as the request makes it: who signs as which side, what they typed and read,
    and where the request came from."""

    side: Signer
    typed_name: str
    text_sha256: str
    code: str
    ip_address: str
    user_agent: str | None


_UNUSABLE: Final[dict[CodeState, type[AppError]]] = {
    CodeState.USED: SigningCodeInvalidError,
    CodeState.LOCKED: SigningCodeLockedError,
    CodeState.EXPIRED: SigningCodeExpiredError,
}


class AgreementSigning:
    def __init__(
        self,
        db: AsyncSession,
        clock: Clock,
        *,
        templates: Templates,
        secret: bytes,
        sender: SigningCodeSender,
        limiter: RateLimiter,
        shows_code: bool,
    ) -> None:
        self._db = db
        self._clock = clock
        self._secret = secret
        self._sender = sender
        self._limiter = limiter
        self._shows_code = shows_code
        self._agreements = RentAgreements(db, clock, templates=templates)
        self._rows = AgreementRepository(db)

    def _code_hash(self, code_row: str, code: str) -> str:
        return keyed_digest(self._secret, purpose="agreement-signing", value=f"{code_row}:{code}")

    async def request_code(
        self,
        actor: Actor,
        booking_code: str,
        *,
        side: Signer,
        ip_address: str | None,
        user_agent: str | None,
    ) -> IssuedCode:
        """A new code for ``actor`` to sign their own booking's agreement as ``side``, replacing
        any code they asked for before."""
        code = f"{secrets.randbelow(10**CODE_DIGITS):0{CODE_DIGITS}d}"
        now = self._clock.now()
        async with self._db.begin():
            booking = await self._agreements.booking_of(actor, booking_code, side=side)
            current = await self._agreements.ensure(booking)
            if current is None:
                raise NotFoundError
            _check_can_sign(current, side)
            agreement = current.row
            wait = resend_wait(
                now=now,
                last_requested_at=await self._rows.last_requested_at(agreement.id, actor.user_id),
            )
            if wait > timedelta(0):
                raise SigningCodeTooSoonError(wait)
            await enforce(self._limiter, SIGNING_CODES_PER_USER, f"user:{actor.user_id}")
            await self._rows.supersede_open(agreement.id, actor.user_id, signer=side, now=now)
            public_id = new_public_id()
            row = SigningCode(
                public_id=public_id,
                agreement_id=agreement.id,
                user_id=actor.user_id,
                signer=side,
                code_hash=self._code_hash(str(public_id), code),
                attempts=0,
                requested_at=now,
                expires_at=now + CODE_TTL,
                ip_address=ip_address,
                user_agent=None if user_agent is None else user_agent[:USER_AGENT_MAX_LENGTH],
            )
            self._rows.add_code(row)
            await self._db.flush()
        try:
            await self._sender.send(actor.user_id, code)
        except Exception as error:
            logger.exception("signing code not sent", user_id=actor.user_id)
            _codes_sent.add(1, {"outcome": "failed"})
            # Undo it, so the wait doesn't hold up a retry straight away.
            async with self._db.begin():
                await self._rows.delete_code(row.id)
            if isinstance(error, AppError):
                raise
            raise ServiceUnavailableError("We couldn't send the code. Please try again.") from None
        _codes_sent.add(1, {"outcome": "sent", "side": side})
        return IssuedCode(
            expires_at=row.expires_at,
            resend_after=now + RESEND_COOLDOWN,
            development_code=code if self._shows_code else None,
        )

    async def sign(self, actor: Actor, booking_code: str, signing: Signing) -> RentAgreement:
        """``actor`` signs their own booking's agreement as ``signing.side``. A wrong code counts
        as an attempt even though it is refused."""
        side = signing.side
        now = self._clock.now()
        refusal: AppError | None = None
        view: RentAgreement | None = None
        async with self._db.begin():
            booking = await self._agreements.booking_of(actor, booking_code, side=side)
            current = await self._agreements.ensure(booking)
            if current is None:
                raise NotFoundError
            _check_can_sign(current, side)
            agreement = current.row
            if signing.text_sha256 != agreement.text_sha256:
                raise AgreementTextChangedError
            challenge = await self._rows.latest_code(agreement.id, actor.user_id, signer=side)
            if challenge is None:
                raise _refused("unknown", SigningCodeInvalidError())
            state = code_state(
                now=now,
                expires_at=challenge.expires_at,
                attempts=challenge.attempts,
                consumed_at=challenge.consumed_at,
                superseded_at=challenge.superseded_at,
            )
            if state is not CodeState.OPEN:
                raise _refused(state, _UNUSABLE[state]())
            expected = self._code_hash(str(challenge.public_id), signing.code)
            if not hmac.compare_digest(challenge.code_hash.encode(), expected.encode()):
                challenge.attempts += 1
                left = attempts_left(challenge.attempts)
                detail = (
                    f"{left} attempts left." if left else "No attempts left; ask for a new code."
                )
                refusal = SigningCodeInvalidError(detail)
            else:
                challenge.consumed_at = now
                await self._rows.sign(
                    AgreementSignature(
                        agreement_id=agreement.id,
                        text_sha256=agreement.text_sha256,
                        template_version=agreement.template_version,
                        signer=side,
                        user_id=actor.user_id,
                        typed_name=signing.typed_name,
                        signed_at=now,
                        ip_address=signing.ip_address,
                        user_agent=None
                        if signing.user_agent is None
                        else signing.user_agent[:USER_AGENT_MAX_LENGTH],
                    )
                )
                agreement.status = transition(AgreementStatus(agreement.status), SIGNS[side])
                if agreement.status == AgreementStatus.SIGNED:
                    agreement.signed_at = now
                await self._db.flush()
                await audit.record(
                    self._db,
                    clock=self._clock,
                    actor=audit.Actor(_AUDIT_ACTORS[side], actor.user_id),
                    action="agreement.signed",
                    entity_type=ENTITY,
                    entity_id=str(agreement.public_id),
                    details={
                        "booking": booking.code,
                        "side": side,
                        "text_sha256": agreement.text_sha256,
                        "template_version": agreement.template_version,
                        "status": agreement.status,
                    },
                    ip_address=_inet(signing.ip_address),
                )
                view = party_view(booking, await self._agreements.reading(booking), side=side)
        # Committed by now: a wrong code counts as an attempt.
        if refusal is not None or view is None:
            raise _refused("wrong_code", refusal or SigningCodeInvalidError())
        _signatures.add(1, {"side": side})
        logger.info("agreement signed", side=side, booking=booking.code)
        return view


def _check_can_sign(current: Current, side: Signer) -> None:
    """Refuse a side that has signed, an agreement that's void or signed by both (409
    INVALID_TRANSITION), and one whose text still lacks something (409 AGREEMENT_NOT_READY)."""
    status = AgreementStatus(current.row.status)
    if not awaits(status, side):
        try:
            transition(status, SIGNS[side])
        except AgreementRefusedError as refusal:
            raise InvalidTransitionError(refusal.reason) from refusal
    if current.missing:
        raise AgreementNotReadyError(
            f"The agreement still needs {' and '.join(current.missing)} before anyone signs."
        )


def _refused(reason: str, error: AppError) -> AppError:
    """Count a refused signing by reason, for alerts on spikes, and hand back the error."""
    _refusals.add(1, {"reason": reason})
    return error


def _inet(value: str) -> str | None:
    """The audit log keeps addresses as INET: anything else stays out of it."""
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None
