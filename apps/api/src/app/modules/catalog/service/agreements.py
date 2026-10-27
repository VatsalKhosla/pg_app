"""The owner agreement (step 2.6, ADR 0025): owners accept the current version by clicking, and ops
see every acceptance.

An acceptance names the version and the SHA-256 of the text the owner was shown, so a version that
changed after they opened it is refused rather than recorded (AGREEMENT_CHANGED). The record keeps
the time, the IP and the user agent, the owner's record keeps the version accepted last, and the
audit log has the acceptance too.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core import audit
from app.core.errors import NotFoundError
from app.modules.catalog.domain.agreements import (
    USER_AGENT_MAX_LENGTH,
    Agreement,
    needs_acceptance,
)
from app.modules.catalog.errors import AgreementChangedError
from app.modules.catalog.models import OwnerAgreement
from app.modules.catalog.repository import CatalogRepository

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.modules.catalog.agreements import AgreementLibrary


@dataclass(frozen=True, slots=True)
class Standing:
    """Where an owner stands with the agreement: the current text, and whether they accepted it."""

    agreement: Agreement
    accepted: bool
    # When they accepted the current text, if they have.
    accepted_at: datetime | None
    accepted_version: str | None


class AgreementService:
    def __init__(
        self,
        db: AsyncSession,
        clock: Clock,
        *,
        library: AgreementLibrary,
        current_version: str,
    ) -> None:
        self._db = db
        self._clock = clock
        self._catalog = CatalogRepository(db)
        current = library.get(current_version)
        if current is None:  # pragma: no cover - the API refuses to start without it
            msg = f"no owner agreement text for version {current_version}"
            raise LookupError(msg)
        self._current = current

    @property
    def current(self) -> Agreement:
        return self._current

    async def standing(self, actor: Actor) -> Standing:
        async with self._db.begin():
            owner = await self._catalog.owner_of_user(actor.user_id)
            if owner is None:
                raise NotFoundError
            accepted_version = owner.agreement_version
            accepted = not needs_acceptance(accepted_version, self._current.version)
            made = (
                await self._catalog.acceptances(owner.id, version=self._current.version)
                if accepted
                else []
            )
        return Standing(
            agreement=self._current,
            accepted=accepted,
            accepted_at=made[0].accepted_at if made else None,
            accepted_version=accepted_version,
        )

    async def accept(
        self,
        actor: Actor,
        *,
        version: str,
        document_sha256: str,
        ip_address: str,
        user_agent: str | None,
    ) -> OwnerAgreement:
        """Record the owner's acceptance of the current agreement, as they were shown it. Accepting
        a version again (a second tab, a repeated click) returns the acceptance already made."""
        if version != self._current.version or document_sha256 != self._current.sha256:
            raise AgreementChangedError
        now = self._clock.now()
        async with self._db.begin():
            # Locked, so two acceptances at once record one.
            owner = await self._catalog.owner_of_user(actor.user_id, lock=True)
            if owner is None:
                raise NotFoundError
            if owner.agreement_version == version:
                made = await self._catalog.acceptances(owner.id, version=version)
                if made:
                    return made[0]
            accepted = await self._catalog.add(
                OwnerAgreement(
                    owner_id=owner.id,
                    version=version,
                    document_sha256=document_sha256,
                    accepted_at=now,
                    accepted_ip=ip_address,
                    accepted_user_agent=None
                    if user_agent is None
                    else user_agent[:USER_AGENT_MAX_LENGTH],
                )
            )
            owner.agreement_version = version
            await self._db.flush()
            await audit.record(
                self._db,
                clock=self._clock,
                actor=audit.Actor("owner", actor.user_id),
                action="catalog.owner_agreement_accepted",
                entity_type="owner",
                entity_id=str(owner.public_id),
                details={"version": version, "document_sha256": document_sha256},
            )
        return accepted

    async def history(self, owner_id: uuid.UUID) -> list[OwnerAgreement]:
        """Every acceptance of an owner's, newest first: for ops."""
        async with self._db.begin():
            owner = await self._catalog.owner(owner_id)
            if owner is None:
                raise NotFoundError
            return await self._catalog.acceptances(owner.id)
