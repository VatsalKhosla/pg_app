"""Authorization rules for the catalog (ARCHITECTURE §12, ADR 0017)."""

from typing import TYPE_CHECKING

from app.core.actor import Role

if TYPE_CHECKING:
    from app.core.actor import Actor


def can_manage_listings(actor: Actor) -> bool:
    """Ops and admins, in a staff session, build and change listings (step 2.4). Field agents
    verify them (step 2.5); owners will manage their own (Phase 7)."""
    return actor.has_role(Role.OPS) or actor.has_role(Role.ADMIN)
