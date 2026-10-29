"""visit analytics id

Revision ID: fce328341fc7
Revises: 4c62184c0a3e
Create Date: 2026-10-29 12:34:46.058719

A visit keeps the anonymous analytics id of the browser the student asked from, if it reports
analytics, so the visit's later steps join the same funnel (ADR 0035).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "fce328341fc7"
down_revision: str | Sequence[str] | None = "4c62184c0a3e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("visits", sa.Column("analytics_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column("visits", "analytics_id")
