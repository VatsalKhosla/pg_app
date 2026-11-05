"""Authorization rules for invoices (ARCHITECTURE §12, ADR 0061)."""

from typing import TYPE_CHECKING

from app.core.actor import Role

if TYPE_CHECKING:
    from app.core.actor import Actor


def can_see_own_invoices(actor: Actor) -> bool:
    """Owners, signed in by phone, see their own; anyone else's is a 404."""
    return actor.has_role(Role.OWNER)


def can_see_invoices(actor: Actor) -> bool:
    """Ops and admins see every owner's."""
    return actor.has_role(Role.OPS) or actor.has_role(Role.ADMIN)
