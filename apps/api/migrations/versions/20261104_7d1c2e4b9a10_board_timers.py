"""board timers

Revision ID: 7d1c2e4b9a10
Revises: ca58345cccc1
Create Date: 2026-11-04 18:00:00.000000

What the bookings board's timers run from (step 5.10, ADR 0054): when a booking's token came in,
and when a dispute was opened, each by the app's clock. The next migration fills them in for rows
that exist already.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7d1c2e4b9a10"
down_revision: str | Sequence[str] | None = "ca58345cccc1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("token_secured_at", sa.DateTime(timezone=True)))
    op.add_column(
        "disputes",
        sa.Column(
            "opened_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.alter_column("disputes", "opened_at", server_default=None)


def downgrade() -> None:
    op.drop_column("disputes", "opened_at")
    op.drop_column("bookings", "token_secured_at")
