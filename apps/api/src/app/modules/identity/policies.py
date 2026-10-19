"""Authorization rules for the identity module: who may do what to which record (ARCHITECTURE §12).

Routes ask a policy and answer 404 when it says no, so nobody learns that someone else's record
exists.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.actor import Actor


def can_end_session(actor: Actor, *, session_user_id: int) -> bool:
    """Users end their own sessions only. Staff tools for other users' sessions come later."""
    return actor.user_id == session_user_id
