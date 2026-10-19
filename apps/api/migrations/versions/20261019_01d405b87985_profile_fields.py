"""profile fields

Revision ID: 01d405b87985
Revises: 69809c8a071a
Create Date: 2026-10-19 22:06:48.272801

The profile of step 1.6 (ARCHITECTURE §6): where people study or work, and, only if they choose to
say, their gender, used to show PGs they can stay in. Both nullable, so existing rows need nothing.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "01d405b87985"
down_revision: str | Sequence[str] | None = "69809c8a071a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("college_or_workplace", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("gender", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_users_gender"), "users", "gender IN ('female', 'male', 'other')"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_gender"), "users", type_="check")
    op.drop_column("users", "gender")
    op.drop_column("users", "college_or_workplace")
