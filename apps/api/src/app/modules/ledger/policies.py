"""Authorization rules for the ledger (ARCHITECTURE §12, ADR 0060)."""

from typing import TYPE_CHECKING

from app.core.actor import Role

if TYPE_CHECKING:
    from app.core.actor import Actor


def can_read_ledger(actor: Actor) -> bool:
    return actor.has_role(Role.OPS) or actor.has_role(Role.ADMIN)
