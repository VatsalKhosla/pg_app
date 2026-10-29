"""Authorization rules for the pricing module (ARCHITECTURE §8.7 and §12)."""

from typing import TYPE_CHECKING

from app.core.actor import Role

if TYPE_CHECKING:
    from app.core.actor import Actor


def can_manage_pricing_policies(actor: Actor) -> bool:
    """Fees, booking terms, caps and rent bands are admins' alone, in a staff session."""
    return actor.has_role(Role.ADMIN)


def can_manage_rule_sets(actor: Actor) -> bool:
    """A PG's pricing rules: ops and admins, in a staff session (owners get the same editor in
    Phase 7)."""
    return actor.has_role(Role.OPS) or actor.has_role(Role.ADMIN)
