"""Authorization rules for payments (ARCHITECTURE §12, ADR 0056)."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.actor import Actor


def can_pay(actor: Actor) -> bool:
    """Whoever may hold a bed pays for their own, signed in by phone. Staff sessions don't: the
    token is the student's to pay. A parent's share link comes in Phase 9."""
    return not actor.is_staff
