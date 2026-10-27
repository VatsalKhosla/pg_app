"""The catalog's events for other modules (ARCHITECTURE §5): outbox jobs written in the change's
own transaction, so they exist exactly when the change commits. app/jobs.py says who handles
each."""

from typing import TYPE_CHECKING, Final

from app.core.outbox import enqueue

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.clock import Clock

INVENTORY_CHANGED: Final = "catalog.inventory_changed"


async def inventory_changed(db: AsyncSession, clock: Clock, property_id: int) -> None:
    """A listing's room categories, rents, rooms or beds changed (search's price summaries
    follow, step 3.1). One job per change: the outbox dedupes a key forever, not per run."""
    await enqueue(db, INVENTORY_CHANGED, {"property_id": property_id}, clock=clock)
