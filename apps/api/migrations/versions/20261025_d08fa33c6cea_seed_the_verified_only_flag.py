"""seed the verified_only flag

Revision ID: d08fa33c6cea
Revises: b0852ff2c4bc
Create Date: 2026-10-25 23:10:00.000000

A data migration, kept apart from the schema migration (backend rules): verified_only, on by
default (BUILD_PLAN 2.5, ADR 0024). Written out here rather than imported from app.core.flags,
so this migration means the same thing however that module changes later.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d08fa33c6cea"
down_revision: str | Sequence[str] | None = "b0852ff2c4bc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KEY = "verified_only"

feature_flags = sa.table(
    "feature_flags",
    sa.column("key", sa.Text()),
    sa.column("value", postgresql.JSONB()),
    sa.column("description", sa.Text()),
)


def upgrade() -> None:
    op.bulk_insert(
        feature_flags,
        [
            {
                "key": KEY,
                "value": True,
                "description": "Only PGs a field agent has verified can be published, and search"
                " shows only those (BUILD_PLAN 2.5).",
            }
        ],
    )


def downgrade() -> None:
    op.execute(feature_flags.delete().where(feature_flags.c.key == KEY))
