"""The append-only audit log for staff, owner and money actions (ARCHITECTURE §17).

``record()`` writes in the caller's transaction, so an action and its audit entry commit together.
The database refuses UPDATE, DELETE and TRUNCATE on ``audit_logs`` (a trigger; see the migration),
so entries can't be edited away, not even by the application. Phone numbers in ``details`` are
masked, and ``entity_id`` must be a public id or code, never personal data.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final, Literal, cast

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, Text, insert, select, text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import AppendOnlyModel
from app.core.pii import mask_pii

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.clock import Clock

type ActorType = Literal["user", "owner", "staff", "system"]


@dataclass(frozen=True, slots=True)
class Actor:
    """Who acted: a student or parent (``user``), an ``owner``, ``staff`` or the ``system``."""

    type: ActorType
    id: int | None = None  # internal users.id; None for the system


SYSTEM: Final = Actor("system")


class AuditLog(AppendOnlyModel):
    __tablename__ = "audit_logs"

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_type: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[int | None] = mapped_column(BigInteger)  # references users from step 1.1
    action: Mapped[str] = mapped_column(Text)  # e.g. "booking.confirm", "refund.approve"
    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[str] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(INET)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))

    __table_args__ = (
        CheckConstraint("actor_type IN ('user', 'owner', 'staff', 'system')", name="actor_type"),
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_created_at", "created_at", postgresql_using="brin"),
    )


async def record(
    session: AsyncSession,
    *,
    clock: Clock,
    actor: Actor,
    action: str,
    entity_type: str,
    entity_id: str,
    details: Mapping[str, object] | None = None,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> None:
    """Append one entry in the caller's transaction."""
    await session.execute(
        insert(AuditLog).values(
            occurred_at=clock.now(),
            actor_type=actor.type,
            actor_id=actor.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            request_id=request_id,
            ip_address=ip_address,
            details=cast("dict[str, Any]", mask_pii(dict(details or {}))),
        )
    )


async def trail(
    session: AsyncSession, *, entity_ids: Collection[str], limit: int = 200
) -> list[AuditLog]:
    """The latest entries about any of ``entity_ids`` (public ids), newest first."""
    if not entity_ids:
        return []
    rows = await session.scalars(
        select(AuditLog)
        .where(AuditLog.entity_id.in_(list(entity_ids)))
        .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
        .limit(limit)
    )
    return list(rows)
