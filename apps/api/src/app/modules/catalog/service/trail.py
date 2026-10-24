"""The audit entry every catalog change writes, in the change's own transaction (ARCHITECTURE
§17): staff, owner and money actions are all audited."""

from typing import TYPE_CHECKING

from app.core import audit

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock


async def staff_did(
    db: AsyncSession,
    clock: Clock,
    actor: Actor,
    action: str,
    *,
    entity: str,
    entity_id: uuid.UUID,
    **details: object,
) -> None:
    await audit.record(
        db,
        clock=clock,
        actor=audit.Actor("staff", actor.user_id),
        action=action,
        entity_type=entity,
        entity_id=str(entity_id),
        details=details,
    )
