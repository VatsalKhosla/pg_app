"""Accounts for other modules (ADR 0021, 0024): the catalog makes an owner's account from their
phone number, and finds the field agents a verification visit can go to. These run inside the
caller's transaction and start none of their own."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.identity.repository import UserRepository

if TYPE_CHECKING:
    import uuid
    from collections.abc import Iterable

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Role
    from app.modules.identity.models import User


@dataclass(frozen=True, slots=True)
class Account:
    id: int
    public_id: uuid.UUID
    phone_e164: str
    name: str | None


def _account(user: User) -> Account:
    return Account(user.id, user.public_id, user.phone_e164, user.name)


class Accounts:
    def __init__(self, db: AsyncSession) -> None:
        self._users = UserRepository(db)

    async def ensure(self, phone_e164: str, *, role: Role, name: str | None = None) -> Account:
        """The account for ``phone_e164``, made if there is none, with ``role`` added if it lacks
        it. ``name`` is used only when the account has none: people keep the name they chose."""
        user, _ = await self._users.get_or_create_by_phone(phone_e164)
        await self._users.add_roles(user.id, [role])
        if name and not user.name:
            user.name = name.strip()
        return _account(user)

    async def find(self, phone_e164: str) -> Account | None:
        user = await self._users.by_phone(phone_e164)
        return None if user is None else _account(user)

    async def many(self, user_ids: Iterable[int]) -> dict[int, Account]:
        return {user.id: _account(user) for user in await self._users.many(user_ids)}

    async def with_role(self, role: Role, *, limit: int = 200) -> list[Account]:
        """Active accounts with ``role``, by name: the field agents a visit can go to, say."""
        return [_account(user) for user in await self._users.with_role(role, limit=limit)]

    async def active_with_role(self, public_id: uuid.UUID, role: Role) -> Account | None:
        """The account with this public id, if it is active and has ``role``."""
        user = await self._users.by_public_id(public_id)
        if user is None or user.status != "active" or role not in await self._users.roles(user.id):
            return None
        return _account(user)
