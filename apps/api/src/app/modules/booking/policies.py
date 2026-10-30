"""Authorization rules for bookings (ARCHITECTURE §12, ADR 0046)."""

from typing import TYPE_CHECKING

from app.core.actor import Role

if TYPE_CHECKING:
    from app.core.actor import Actor


def can_book(actor: Actor) -> bool:
    """Students and parents, signed in by phone, hold beds and see their own bookings. Staff
    sessions don't: an agent reserves for a student from their visit (5.9)."""
    return not actor.is_staff


def can_answer_as_owner(actor: Actor) -> bool:
    """Owners, signed in by phone, see and answer their own PGs' bookings (step 5.4)."""
    return actor.has_role(Role.OWNER)


def can_run_bookings(actor: Actor) -> bool:
    """Ops and admins see every booking, and answer one for its owner."""
    return actor.has_role(Role.OPS) or actor.has_role(Role.ADMIN)
