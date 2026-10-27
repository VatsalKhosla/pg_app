"""Authorization rules for the catalog (ARCHITECTURE §12, ADR 0017)."""

from typing import TYPE_CHECKING

from app.core.actor import Role

if TYPE_CHECKING:
    from app.core.actor import Actor


def can_manage_listings(actor: Actor) -> bool:
    """Ops and admins, in a staff session, build and change listings (step 2.4). Field agents
    verify them (step 2.5, below); owners will manage their own (Phase 7)."""
    return actor.has_role(Role.OPS) or actor.has_role(Role.ADMIN)


def can_manage_verification(actor: Actor) -> bool:
    """Ops and admins book, cancel and read every visit, and suspend a verification (ADR 0024)."""
    return can_manage_listings(actor)


def can_make_visits(actor: Actor) -> bool:
    """Field agents, in a staff session, see the visits booked for them and report on them."""
    return actor.has_role(Role.FIELD_AGENT)


def can_act_as_owner(actor: Actor) -> bool:
    """Owners, signed in by phone, see their own record and accept the owner agreement."""
    return actor.has_role(Role.OWNER)
