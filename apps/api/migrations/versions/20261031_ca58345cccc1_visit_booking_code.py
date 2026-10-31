"""visit booking code

Revision ID: ca58345cccc1
Revises: 85bcc3e7caff
Create Date: 2026-10-31 19:10:50.204084

The booking a student made on the spot from a visit (step 5.9, ADR 0053): the visit log's link
to it. Nullable, so existing visits need nothing.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ca58345cccc1"
down_revision: str | Sequence[str] | None = "85bcc3e7caff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("visits", sa.Column("booking_code", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("visits", "booking_code")
