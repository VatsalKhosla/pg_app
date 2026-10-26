"""verification photo purpose

Revision ID: d928f0d105f9
Revises: 929c70696e3d
Create Date: 2026-10-25 22:40:00.000000

Media gains a purpose for field agents' evidence from verification visits (step 2.5, ADR 0024):
kept private like documents, prepared like photos.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d928f0d105f9"
down_revision: str | Sequence[str] | None = "929c70696e3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEFORE = ("listing_photo", "listing_video", "document")
AFTER = (*BEFORE, "verification_photo")


def _purposes(values: Sequence[str]) -> str:
    listed = ", ".join(f"'{value}'" for value in values)
    return f"purpose IN ({listed})"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_media_assets_purpose"), "media_assets", type_="check")
    op.create_check_constraint(op.f("ck_media_assets_purpose"), "media_assets", _purposes(AFTER))


def downgrade() -> None:
    # Refused while any verification photo exists: those rows must be dealt with first.
    op.drop_constraint(op.f("ck_media_assets_purpose"), "media_assets", type_="check")
    op.create_check_constraint(op.f("ck_media_assets_purpose"), "media_assets", _purposes(BEFORE))
