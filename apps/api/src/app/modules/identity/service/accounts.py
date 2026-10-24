"""Accounts for other modules (ADR 0021): the catalog makes an owner's account from their phone
number. These run inside the caller's transaction and start none of their own."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.identity.repository import UserRepository

if TYPE_CHECKING:
    import uuid
    from collections.abc import Iterable

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Role


@dataclass(frozen=True, slots=True)
class Account:
    id: int
    public_id: uuid.UUID
    phone_e164: str
    name: str | None


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
        return Account(user.id, user.public_id, user.phone_e164, user.name)

    async def find(self, phone_e164: str) -> Account | None:
        user = await self._users.by_phone(phone_e164)
        return (
            None if user is None else Account(user.id, user.public_id, user.phone_e164, user.name)
        )

    async def many(self, user_ids: Iterable[int]) -> dict[int, Account]:
        return {
            user.id: Account(user.id, user.public_id, user.phone_e164, user.name)
            for user in await self._users.many(user_ids)
        }
