"""dispute photo purpose

Revision ID: b059d241c6b2
Revises: 39a351f84ffb
Create Date: 2026-10-31 13:56:40.643899

Media gains a purpose for a student's evidence that their room isn't as shown (step 5.7,
ADR 0051): kept private like documents, prepared like photos.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b059d241c6b2"
down_revision: str | Sequence[str] | None = "39a351f84ffb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEFORE = ("listing_photo", "listing_video", "document", "verification_photo")
AFTER = (*BEFORE, "dispute_photo")


def _purposes(values: Sequence[str]) -> str:
    listed = ", ".join(f"'{value}'" for value in values)
    return f"purpose IN ({listed})"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_media_assets_purpose"), "media_assets", type_="check")
    op.create_check_constraint(op.f("ck_media_assets_purpose"), "media_assets", _purposes(AFTER))


def downgrade() -> None:
    # Refused while any dispute photo exists: those rows must be dealt with first.
    op.drop_constraint(op.f("ck_media_assets_purpose"), "media_assets", type_="check")
    op.create_check_constraint(op.f("ck_media_assets_purpose"), "media_assets", _purposes(BEFORE))
