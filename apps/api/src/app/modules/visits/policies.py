"""Authorization rules for visits (ARCHITECTURE §12, ADR 0033)."""

from typing import TYPE_CHECKING

from app.core.actor import Role

if TYPE_CHECKING:
    from app.core.actor import Actor


def can_request_visits(actor: Actor) -> bool:
    """Students and parents, signed in by phone, ask to visit PGs and see their own visits.
    Staff sessions don't: staff book visits for students through ops."""
    return not actor.is_staff


def can_schedule_visits(actor: Actor) -> bool:
    """Ops and admins see every visit, book a time and an agent, and cancel."""
    return actor.has_role(Role.OPS) or actor.has_role(Role.ADMIN)


def can_run_visits(actor: Actor) -> bool:
    """Field agents see the visits booked for them, check in and record how they went."""
    return actor.has_role(Role.FIELD_AGENT)
