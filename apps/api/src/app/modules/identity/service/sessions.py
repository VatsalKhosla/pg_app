"""Sessions (ARCHITECTURE §12): who is signed in, on which browser, until when.

A session token is 256 random bits, sent to the browser once, in an HttpOnly cookie. The database
keeps only its SHA-256, so a leaked table holds no token anyone could use. A random token needs
no salt or key: it can't be guessed from its hash. Each service method is one transaction.
"""

import hashlib
import ipaddress
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final

from app.core.actor import STAFF_ROLES, Actor, Role
from app.modules.identity.domain.sessions import (
    POLICIES,
    EndReason,
    SessionKind,
    absolute_expiry,
    is_due_for_touch,
    sliding_expiry,
)
from app.modules.identity.models import UserSession
from app.modules.identity.policies import can_end_session
from app.modules.identity.repository import SessionRepository, UserRepository

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.clock import Clock

TOKEN_BYTES: Final = 32
# secrets.token_urlsafe(32): 43 characters of base64url. Anything else is refused unhashed.
_TOKEN_SHAPE: Final = re.compile(r"[A-Za-z0-9_-]{43}")
_MAX_USER_AGENT_LENGTH: Final = 512
# Ended and expired sessions (with their IP address and user agent) are kept this long, for
# investigating abuse, then deleted (DPDP: no longer than needed).
SESSION_RETENTION: Final = timedelta(days=30)


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def _clean_ip(value: str | None) -> str | None:
    try:
        return None if value is None else str(ipaddress.ip_address(value))
    except ValueError:
        return None


@dataclass(frozen=True)
class IssuedSession:
    """A new token. It goes into the cookie and nowhere else: never log it."""

    token: str
    public_id: uuid.UUID
    expires_at: datetime


@dataclass(frozen=True)
class Authentication:
    actor: Actor
    expires_at: datetime
    # The expiry moved forward, so the cookie should be sent again with the new lifetime.
    refreshed: bool


class SessionService:
    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._db = db
        self._clock = clock
        self._sessions = SessionRepository(db)
        self._users = UserRepository(db)

    async def start(
        self,
        user_id: int,
        *,
        kind: SessionKind,
        ip_address: str | None,
        user_agent: str | None,
        replacing: str | None = None,
    ) -> IssuedSession:
        """Sign ``user_id`` in on this browser. ``replacing`` is the browser's previous session
        token, if any: it ends, so a token planted before sign-in is never upgraded (session
        fixation)."""
        now = self._clock.now()
        policy = POLICIES[kind]
        absolute = absolute_expiry(policy, started_at=now)
        token = secrets.token_urlsafe(TOKEN_BYTES)
        session = UserSession(
            user_id=user_id,
            token_hash=hash_token(token),
            kind=kind,
            started_at=now,
            last_seen_at=now,
            expires_at=sliding_expiry(policy, now=now, absolute_expires_at=absolute),
            absolute_expires_at=absolute,
            ip_address=_clean_ip(ip_address),
            user_agent=None if user_agent is None else user_agent[:_MAX_USER_AGENT_LENGTH],
        )
        async with self._db.begin():
            if replacing is not None:
                await self._sessions.end_by_token(
                    hash_token(replacing), reason=EndReason.REPLACED, now=now
                )
            self._sessions.add(session)
        return IssuedSession(
            token=token, public_id=session.public_id, expires_at=session.expires_at
        )

    async def authenticate(self, token: str) -> Authentication | None:
        """The actor behind a session token, or None if it is unknown, ended or expired, or the
        user is suspended. Activity slides the expiry forward (at most every few minutes)."""
        if not _TOKEN_SHAPE.fullmatch(token):
            return None
        now = self._clock.now()
        async with self._db.begin():
            session = await self._sessions.find_live(hash_token(token), now=now)
            if session is None:
                return None
            user = await self._users.get(session.user_id)
            if user is None or user.status != "active":
                return None
            policy = POLICIES[SessionKind(session.kind)]
            refreshed = is_due_for_touch(policy, now=now, last_seen_at=session.last_seen_at)
            if refreshed:
                session.last_seen_at = now
                session.expires_at = sliding_expiry(
                    policy, now=now, absolute_expires_at=session.absolute_expires_at
                )
            roles = await self._users.roles(user.id)
            if session.kind == SessionKind.USER:
                # Staff authority comes only from staff sign-in (12-hour sessions); a phone-OTP
                # session never carries it, even for a staff member's account.
                roles -= STAFF_ROLES
            elif roles.isdisjoint(STAFF_ROLES):
                # A staff session works only while its user is staff.
                return None
            actor = Actor(
                user_id=user.id,
                user_public_id=user.public_id,
                roles=roles,
                session_id=session.id,
                session_public_id=session.public_id,
            )
            return Authentication(actor=actor, expires_at=session.expires_at, refreshed=refreshed)

    async def rotate(self, token: str) -> IssuedSession | None:
        """Give a live session a new token and retire the old one (after sign-in or a role
        change). The session itself, and its place in the session list, stay the same."""
        if not _TOKEN_SHAPE.fullmatch(token):
            return None
        now = self._clock.now()
        new_token = secrets.token_urlsafe(TOKEN_BYTES)
        async with self._db.begin():
            session = await self._sessions.find_live(hash_token(token), now=now)
            if session is None:
                return None
            session.token_hash = hash_token(new_token)
            session.rotated_at = now
        return IssuedSession(
            token=new_token, public_id=session.public_id, expires_at=session.expires_at
        )

    async def end(self, token: str, *, reason: EndReason = EndReason.LOGOUT) -> None:
        async with self._db.begin():
            await self._sessions.end_by_token(
                hash_token(token), reason=reason, now=self._clock.now()
            )

    async def end_everywhere(self, actor: Actor) -> int:
        async with self._db.begin():
            return await self._sessions.end_for_user(
                actor.user_id, reason=EndReason.LOGOUT_EVERYWHERE, now=self._clock.now()
            )

    async def end_one(self, actor: Actor, session_public_id: uuid.UUID) -> bool:
        """End one of the actor's sessions; False if there is none they may end."""
        now = self._clock.now()
        async with self._db.begin():
            session = await self._sessions.by_public_id(session_public_id)
            if session is None or not can_end_session(actor, session_user_id=session.user_id):
                return False
            if session.ended_at is None:
                session.ended_at = now
                session.end_reason = EndReason.ENDED_BY_USER
            return True

    async def live_sessions(self, actor: Actor) -> list[UserSession]:
        async with self._db.begin():
            return await self._sessions.live_for_user(actor.user_id, now=self._clock.now())


@dataclass(frozen=True)
class Profile:
    public_id: uuid.UUID
    phone_e164: str
    email: str | None
    name: str | None
    roles: frozenset[Role]


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._users = UserRepository(db)

    async def profile(self, user_id: int) -> Profile | None:
        async with self._db.begin():
            user = await self._users.get(user_id)
            if user is None:
                return None
            return Profile(
                public_id=user.public_id,
                phone_e164=user.phone_e164,
                email=user.email,
                name=user.name,
                roles=await self._users.roles(user.id),
            )


async def delete_finished_sessions(db: AsyncSession, clock: Clock) -> int:
    """Retention: drop sessions that ended or expired more than SESSION_RETENTION ago."""
    return await SessionRepository(db).delete_finished(before=clock.now() - SESSION_RETENTION)
