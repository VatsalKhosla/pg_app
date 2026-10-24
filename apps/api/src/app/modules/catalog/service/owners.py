"""Owners (ADR 0021): staff add the businesses that list PGs, by the owner's phone number. The
account is made if the owner hasn't signed in yet; they sign in with that phone later."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.actor import Role
from app.core.pagination import split_page
from app.modules.catalog.domain.owners import (
    NAME_MAX_LENGTH,
    KycStatus,
    OwnerStatus,
    normalize_gstin,
)
from app.modules.catalog.errors import OwnerExistsError
from app.modules.catalog.models import Owner
from app.modules.catalog.repository import CatalogRepository
from app.modules.catalog.service.checks import check, text_problems
from app.modules.catalog.service.trail import staff_did
from app.modules.identity.domain.phones import normalize_indian_mobile
from app.modules.identity.service import Account, Accounts

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.core.pagination import PageRequest


@dataclass(frozen=True, slots=True)
class OwnerRecord:
    owner: Owner
    account: Account | None


class OwnerService:
    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._db = db
        self._clock = clock
        self._catalog = CatalogRepository(db)
        self._accounts = Accounts(db)

    async def add(
        self,
        actor: Actor,
        *,
        phone: str,
        legal_name: str,
        business_name: str,
        gstin: str | None = None,
        name: str | None = None,
    ) -> OwnerRecord:
        phone_e164 = normalize_indian_mobile(phone)
        problems = [] if phone_e164 is not None else ["that isn't an Indian mobile number"]
        problems += text_problems(
            "the legal name", legal_name, required=True, max_length=NAME_MAX_LENGTH
        )
        problems += text_problems(
            "the business name", business_name, required=True, max_length=NAME_MAX_LENGTH
        )
        if name is not None:
            problems += text_problems("the name", name, required=False, max_length=NAME_MAX_LENGTH)
        normalized = None if gstin is None else normalize_gstin(gstin)
        if gstin is not None and normalized is None:
            problems.append("that isn't a GSTIN")
        check(problems)
        assert phone_e164 is not None  # noqa: S101 - checked above
        async with self._db.begin():
            account = await self._accounts.ensure(phone_e164, role=Role.OWNER, name=name)
            if await self._catalog.owner_of_user(account.id) is not None:
                raise OwnerExistsError
            owner = await self._catalog.add(
                Owner(
                    user_id=account.id,
                    legal_name=legal_name.strip(),
                    business_name=business_name.strip(),
                    gstin=normalized,
                    kyc_status=KycStatus.NOT_STARTED,
                    status=OwnerStatus.ACTIVE,
                )
            )
            await staff_did(
                self._db,
                self._clock,
                actor,
                "catalog.owner_added",
                entity="owner",
                entity_id=owner.public_id,
            )
        return OwnerRecord(owner, account)

    async def page(
        self, request: PageRequest, *, text: str | None = None
    ) -> tuple[list[OwnerRecord], uuid.UUID | None]:
        """Owners in public-id order; ``text`` finds a phone number exactly, or names partly."""
        async with self._db.begin():
            phone = None if text is None else normalize_indian_mobile(text)
            user_id = None
            if phone is not None:
                account = await self._accounts.find(phone)
                if account is None:
                    return [], None
                user_id = account.id
            rows = await self._catalog.owners_page(
                after=request.after,
                limit=request.limit,
                text=None if phone is not None else text,
                user_id=user_id,
            )
            owners, next_cursor = split_page(rows, request, cursor_of=lambda owner: owner.public_id)
            accounts = await self._accounts.many(owner.user_id for owner in owners)
        return [OwnerRecord(owner, accounts.get(owner.user_id)) for owner in owners], next_cursor
