"""Authorization rules for bookings (ARCHITECTURE §12, ADR 0046)."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.actor import Actor


def can_book(actor: Actor) -> bool:
    """Students and parents, signed in by phone, hold beds and see their own bookings. Staff
    sessions don't: an agent reserves for a student from their visit (5.9)."""
    return not actor.is_staff
