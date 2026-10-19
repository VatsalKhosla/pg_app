"""Authorization rules for the compliance module (ARCHITECTURE §12, ADR 0017)."""

from typing import TYPE_CHECKING

from app.core.actor import Role

if TYPE_CHECKING:
    from app.core.actor import Actor


def can_see_data_request(actor: Actor, *, owner_id: int) -> bool:
    """A data request, and an export's file, are for the person who asked: not even staff
    download someone's export."""
    return actor.user_id == owner_id


def can_review_data_requests(actor: Actor) -> bool:
    """The queue is for ops and admins, in a staff session."""
    return actor.has_role(Role.OPS) or actor.has_role(Role.ADMIN)
