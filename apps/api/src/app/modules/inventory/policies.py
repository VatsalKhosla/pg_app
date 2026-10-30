"""Authorization rules for the inventory module (ARCHITECTURE §12)."""

from typing import TYPE_CHECKING

from app.core.actor import Role

if TYPE_CHECKING:
    from app.core.actor import Actor


def can_manage_inventory(actor: Actor) -> bool:
    """Offline tenants and maintenance: ops and admins, in a staff session (owners in Phase 7)."""
    return actor.has_role(Role.OPS) or actor.has_role(Role.ADMIN)
