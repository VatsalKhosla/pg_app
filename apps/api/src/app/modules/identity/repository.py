"""Queries on the identity module's tables. Repositories never commit; services own transactions."""

from typing import TYPE_CHECKING

from sqlalchemy import delete, or_, select, update

from app.core.actor import Role
from app.modules.identity.models import User, UserRole, UserSession

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

    async def roles(self, user_id: int) -> frozenset[Role]:
        rows = await self._db.scalars(select(UserRole.role).where(UserRole.user_id == user_id))
        return frozenset(Role(role) for role in rows)


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
