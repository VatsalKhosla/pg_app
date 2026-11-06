"""Authorization rules for insights (ARCHITECTURE §12, ADR 0063)."""

from typing import TYPE_CHECKING

from app.core.actor import Role

if TYPE_CHECKING:
    from app.core.actor import Actor


def can_see_own_insights(actor: Actor) -> bool:
    """Owners, signed in by phone, see their own PGs' numbers; the service checks the PG."""
    return actor.has_role(Role.OWNER)
