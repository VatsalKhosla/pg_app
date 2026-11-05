"""Authorization rules for payments (ARCHITECTURE §12, ADR 0056)."""

from typing import TYPE_CHECKING

from app.core.actor import Role

if TYPE_CHECKING:
    from app.core.actor import Actor


def can_refund(actor: Actor) -> bool:
    """Ops and admins see every payment, and give money back with a reason."""
    return actor.has_role(Role.OPS) or actor.has_role(Role.ADMIN)


def can_pay(actor: Actor) -> bool:
    """Whoever may hold a bed pays for their own, signed in by phone. Staff sessions don't: the
    token is the student's to pay. A parent's share link comes in Phase 9."""
    return not actor.is_staff


def can_reconcile(actor: Actor) -> bool:
    """Ops and admins check payments against the gateway, and close what they've looked at."""
    return actor.has_role(Role.OPS) or actor.has_role(Role.ADMIN)


def can_pay_invoices(actor: Actor) -> bool:
    """Owners, signed in by phone, pay their own invoices (step 6.5)."""
    return actor.has_role(Role.OWNER)
