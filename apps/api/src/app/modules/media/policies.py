"""Authorization rules for media (ARCHITECTURE §12, ADR 0017)."""

from typing import TYPE_CHECKING

from app.core.actor import Role
from app.modules.media.domain.assets import Purpose

if TYPE_CHECKING:
    from app.core.actor import Actor


def can_upload(actor: Actor, purpose: Purpose) -> bool:
    """Staff, in a staff session, upload listing media and documents for now; owners and
    students get their own uploads with the features that need them."""
    return actor.is_staff and purpose in Purpose


def can_finish(actor: Actor, *, uploaded_by: int | None) -> bool:
    """Only the uploader says an upload is done."""
    return actor.user_id == uploaded_by


def can_view(actor: Actor, *, uploaded_by: int | None) -> bool:
    """The uploader, and ops and admins in a staff session; anyone else gets a 404."""
    return actor.user_id == uploaded_by or actor.has_role(Role.OPS) or actor.has_role(Role.ADMIN)


def is_verified_capture(actor: Actor, purpose: Purpose) -> bool:
    """Listing photos and videos a field agent takes are shown as verified (ARCHITECTURE §13)."""
    return actor.has_role(Role.FIELD_AGENT) and purpose in {
        Purpose.LISTING_PHOTO,
        Purpose.LISTING_VIDEO,
    }
