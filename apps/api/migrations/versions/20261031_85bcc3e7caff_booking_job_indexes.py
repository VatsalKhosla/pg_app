"""booking job indexes

Revision ID: 85bcc3e7caff
Revises: a08fc9363e39
Create Date: 2026-10-31 18:45:34.667370

Partial indexes for the booking jobs' scans (step 5.8, ADR 0052): owners' deadlines on
bookings with the token in, check windows on bookings checked in, and move-ins on confirmed
bookings. Holds already have theirs.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "85bcc3e7caff"
down_revision: str | Sequence[str] | None = "a08fc9363e39"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_bookings_checked_in",
        "bookings",
        ["check_window_ends_at"],
        unique=False,
        postgresql_where=sa.text("status = 'checked_in'"),
    )
    op.create_index(
        "ix_bookings_confirmed",
        "bookings",
        ["move_in"],
        unique=False,
        postgresql_where=sa.text("status = 'confirmed'"),
    )
    op.create_index(
        "ix_bookings_token_secured",
        "bookings",
        ["confirm_by"],
        unique=False,
        postgresql_where=sa.text("status = 'token_secured'"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_bookings_token_secured",
        table_name="bookings",
        postgresql_where=sa.text("status = 'token_secured'"),
    )
    op.drop_index(
        "ix_bookings_confirmed",
        table_name="bookings",
        postgresql_where=sa.text("status = 'confirmed'"),
    )
    op.drop_index(
        "ix_bookings_checked_in",
        table_name="bookings",
        postgresql_where=sa.text("status = 'checked_in'"),
    )
