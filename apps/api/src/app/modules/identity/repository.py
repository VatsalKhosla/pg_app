"""Queries on the identity module's tables. Repositories never commit; services own transactions."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from app.core.actor import STAFF_ROLES, Role
from app.core.ids import new_public_id
from app.modules.identity.domain.staff import IdentityProvider
from app.modules.identity.models import (
    OtpChallenge,
    TotpCredential,
    User,
    UserIdentity,
    UserRole,
    UserSession,
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import Iterable
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.identity.domain.sessions import EndReason


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def add(self, *, phone_e164: str, roles: Iterable[Role]) -> User:
        user = User(phone_e164=phone_e164)
        self._db.add(user)
        await self._db.flush()
        self._db.add_all(UserRole(user_id=user.id, role=role) for role in roles)
        await self._db.flush()
        return user

    async def get(self, user_id: int) -> User | None:
        return await self._db.get(User, user_id)

    async def get_or_create_by_phone(self, phone_e164: str) -> tuple[User, bool]:
        """The account for ``phone_e164``, created (without roles) if there is none yet. Safe when
        two sign-ins for the same phone race. Returns the user and whether it was created."""
        created_id = await self._db.scalar(
            insert(User)
            .values(phone_e164=phone_e164, public_id=new_public_id())
            .on_conflict_do_nothing(index_elements=[User.phone_e164])
            .returning(User.id)
        )
        user = (
            await self._db.execute(select(User).where(User.phone_e164 == phone_e164))
        ).scalar_one()
        return user, created_id is not None

    async def roles(self, user_id: int) -> frozenset[Role]:
        rows = await self._db.scalars(select(UserRole.role).where(UserRole.user_id == user_id))
        return frozenset(Role(role) for role in rows)

    async def by_phone(self, phone_e164: str) -> User | None:
        return await self._db.scalar(select(User).where(User.phone_e164 == phone_e164))

    async def by_email(self, email: str) -> User | None:
        """The user with this address, compared without regard to case (citext)."""
        return await self._db.scalar(select(User).where(User.email == email))

    async def add_roles(self, user_id: int, roles: Iterable[Role]) -> None:
        values = [{"user_id": user_id, "role": role} for role in roles]
        if values:
            await self._db.execute(
                insert(UserRole)
                .values(values)
                .on_conflict_do_nothing(index_elements=[UserRole.user_id, UserRole.role])
            )

    async def remove_roles(self, user_id: int, roles: Iterable[Role]) -> None:
        await self._db.execute(
            delete(UserRole).where(UserRole.user_id == user_id, UserRole.role.in_(list(roles)))
        )

    async def staff_page(self, *, after: uuid.UUID | None, limit: int) -> list[StaffRecord]:
        """Users with a staff role, in public-id order, after ``after``: ``limit + 1`` rows at
        most, so the caller can tell whether another page follows. One query, however many."""
        google_email = (
            select(UserIdentity.email)
            .where(
                UserIdentity.user_id == User.id, UserIdentity.provider == IdentityProvider.GOOGLE
            )
            .scalar_subquery()
        )
        authenticator = (
            select(TotpCredential.id)
            .where(TotpCredential.user_id == User.id, TotpCredential.confirmed_at.is_not(None))
            .exists()
        )
        query = (
            select(User, func.array_agg(UserRole.role), google_email, authenticator)
            .join(UserRole, UserRole.user_id == User.id)
            .where(UserRole.role.in_(sorted(STAFF_ROLES)))
            .group_by(User.id)
            .order_by(User.public_id)
            .limit(limit + 1)
        )
        if after is not None:
            query = query.where(User.public_id > after)
        rows = await self._db.execute(query)
        return [
            StaffRecord(
                user=user,
                roles=frozenset(Role(role) for role in roles),
                google_email=email,
                authenticator=enrolled,
            )
            for user, roles, email, enrolled in rows
        ]


@dataclass(frozen=True)
class StaffRecord:
    """A staff member for the staff list: their staff roles and how they can sign in."""

    user: User
    roles: frozenset[Role]
    # The linked Google account's address, if any.
    google_email: str | None
    # Whether a confirmed authenticator app is set up.
    authenticator: bool


class SessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    def add(self, session: UserSession) -> None:
        self._db.add(session)

    async def find_live(self, token_hash: bytes, *, now: datetime) -> UserSession | None:
        """The session with this token if it hasn't ended or expired, locked for update."""
        return await self._db.scalar(
            select(UserSession)
            .where(
                UserSession.token_hash == token_hash,
                UserSession.ended_at.is_(None),
                UserSession.expires_at > now,
            )
            .with_for_update()
        )

    async def live_for_user(self, user_id: int, *, now: datetime) -> list[UserSession]:
        rows = await self._db.scalars(
            select(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.ended_at.is_(None),
                UserSession.expires_at > now,
            )
            .order_by(UserSession.last_seen_at.desc())
        )
        return list(rows)

    async def by_public_id(self, public_id: uuid.UUID) -> UserSession | None:
        return await self._db.scalar(select(UserSession).where(UserSession.public_id == public_id))

    async def end_by_token(self, token_hash: bytes, *, reason: EndReason, now: datetime) -> int:
        ended = await self._db.scalars(
            update(UserSession)
            .where(UserSession.token_hash == token_hash, UserSession.ended_at.is_(None))
            .values(ended_at=now, end_reason=reason)
            .returning(UserSession.id)
        )
        return len(ended.all())

    async def end_for_user(self, user_id: int, *, reason: EndReason, now: datetime) -> int:
        ended = await self._db.scalars(
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.ended_at.is_(None))
            .values(ended_at=now, end_reason=reason)
            .returning(UserSession.id)
        )
        return len(ended.all())

    async def delete_finished(self, *, before: datetime) -> int:
        """Delete sessions that ended or expired before ``before`` (retention)."""
        deleted = await self._db.scalars(
            delete(UserSession)
            .where(or_(UserSession.ended_at < before, UserSession.expires_at < before))
            .returning(UserSession.id)
        )
        return len(deleted.all())


class OtpRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    def add(self, challenge: OtpChallenge) -> None:
        self._db.add(challenge)

    async def lock_phone(self, phone_e164: str) -> None:
        """Serialise code requests for one phone until the transaction ends, so two requests
        racing past the resend cooldown can't both send a code."""
        await self._db.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended("otp:" + phone_e164, 0)))
        )

    async def last_requested_at(self, phone_e164: str, *, purpose: str) -> datetime | None:
        return await self._db.scalar(
            select(func.max(OtpChallenge.requested_at)).where(
                OtpChallenge.phone_e164 == phone_e164, OtpChallenge.purpose == purpose
            )
        )

    async def supersede_open(self, phone_e164: str, *, purpose: str, now: datetime) -> None:
        await self._db.execute(
            update(OtpChallenge)
            .where(
                OtpChallenge.phone_e164 == phone_e164,
                OtpChallenge.purpose == purpose,
                OtpChallenge.consumed_at.is_(None),
                OtpChallenge.superseded_at.is_(None),
            )
            .values(superseded_at=now)
        )

    async def by_public_id_for_update(self, public_id: uuid.UUID) -> OtpChallenge | None:
        return await self._db.scalar(
            select(OtpChallenge).where(OtpChallenge.public_id == public_id).with_for_update()
        )

    async def delete(self, challenge_id: int) -> None:
        await self._db.execute(delete(OtpChallenge).where(OtpChallenge.id == challenge_id))

    async def delete_requested_before(self, before: datetime) -> int:
        deleted = await self._db.scalars(
            delete(OtpChallenge)
            .where(OtpChallenge.requested_at < before)
            .returning(OtpChallenge.id)
        )
        return len(deleted.all())


class IdentityRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    def add(self, identity: UserIdentity) -> None:
        self._db.add(identity)

    async def find(self, provider: IdentityProvider, subject: str) -> UserIdentity | None:
        return await self._db.scalar(
            select(UserIdentity).where(
                UserIdentity.provider == provider, UserIdentity.subject == subject
            )
        )

    async def for_user(self, user_id: int, provider: IdentityProvider) -> UserIdentity | None:
        return await self._db.scalar(
            select(UserIdentity).where(
                UserIdentity.user_id == user_id, UserIdentity.provider == provider
            )
        )

    async def delete_for_user(self, user_id: int, provider: IdentityProvider) -> bool:
        deleted = await self._db.scalars(
            delete(UserIdentity)
            .where(UserIdentity.user_id == user_id, UserIdentity.provider == provider)
            .returning(UserIdentity.id)
        )
        return bool(deleted.all())


class TotpRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def for_user(self, user_id: int, *, for_update: bool = False) -> TotpCredential | None:
        query = select(TotpCredential).where(TotpCredential.user_id == user_id)
        return await self._db.scalar(query.with_for_update() if for_update else query)

    async def replace(self, user_id: int, *, salt: bytes) -> TotpCredential:
        """A new, unconfirmed credential for ``user_id``, in place of any earlier one."""
        await self.delete_for_user(user_id)
        credential = TotpCredential(user_id=user_id, salt=salt)
        self._db.add(credential)
        await self._db.flush()
        return credential

    async def delete_for_user(self, user_id: int) -> bool:
        deleted = await self._db.scalars(
            delete(TotpCredential)
            .where(TotpCredential.user_id == user_id)
            .returning(TotpCredential.id)
        )
        return bool(deleted.all())
