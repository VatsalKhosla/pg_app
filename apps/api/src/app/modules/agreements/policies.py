"""Authorization rules for rent agreements and police verification (ARCHITECTURE §12, ADR 0070).

Who may ask is decided here; whose booking it is, by the services, which answer 404 for anyone
else's, as if it didn't exist.
"""

from typing import TYPE_CHECKING

from app.core.actor import Role

if TYPE_CHECKING:
    from app.core.actor import Actor


def can_sign_as_student(actor: Actor) -> bool:
    """The person who booked, signed in by phone, as they hold and see their bookings. Staff
    sessions never sign for a student."""
    return not actor.is_staff


def can_sign_as_owner(actor: Actor) -> bool:
    """An owner, signed in by phone, for their own PGs' bookings."""
    return actor.has_role(Role.OWNER)


def can_read_everything(actor: Actor) -> bool:
    """Ops and admins, in a staff session, read every agreement and verification, and change
    none: the student and the owner sign, and only they move a verification on."""
    return actor.has_role(Role.OPS) or actor.has_role(Role.ADMIN)
