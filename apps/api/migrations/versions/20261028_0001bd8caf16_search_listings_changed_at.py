"""search listings changed at

Revision ID: 0001bd8caf16
Revises: e6b2a9d4c1f8
Create Date: 2026-10-28 17:21:15.606064

When the catalog last said a listing changed, for the sitemap's lastmod (ADR 0032). Null until
then: the sitemap falls back to when the listing was published, so nothing needs filling in.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001bd8caf16"
down_revision: str | Sequence[str] | None = "e6b2a9d4c1f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "search_listings", sa.Column("changed_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("search_listings", "changed_at")
