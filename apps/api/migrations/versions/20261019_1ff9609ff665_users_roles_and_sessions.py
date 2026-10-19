"""users, roles and sessions

Revision ID: 1ff9609ff665
Revises: 7d2931b42327
Create Date: 2026-10-19 13:29:43.963722

The identity tables of step 1.1 (ARCHITECTURE §6, §12). ``sessions`` stores only the SHA-256 of
each session token (unique), so the table holds no usable token.
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "1ff9609ff665"
down_revision: str | Sequence[str] | None = "7d2931b42327"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _identity() -> sa.Column[int]:
    return sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False)


def _timestamps() -> list[sa.Column[datetime]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _user_id() -> sa.Column[int]:
    return sa.Column(
        "user_id",
        sa.BigInteger(),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "users",
        _identity(),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("phone_e164", sa.Text(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        *_timestamps(),
        sa.CheckConstraint("phone_e164 ~ '^\\+[1-9][0-9]{6,14}$'", name="phone_e164"),
        sa.CheckConstraint("status IN ('active', 'suspended')", name="status"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("phone_e164"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_table(
        "user_roles",
        _identity(),
        _user_id(),
        sa.Column("role", sa.Text(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "role IN ('student', 'parent', 'owner', 'field_agent', 'ops', 'admin')", name="role"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_roles")),
        sa.UniqueConstraint("user_id", "role"),
    )
    op.create_table(
        "sessions",
        _identity(),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        _user_id(),
        sa.Column("token_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_reason", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("kind IN ('user', 'staff')", name="kind"),
        sa.CheckConstraint(
            "end_reason IN ('logout', 'logout_everywhere', 'ended_by_user', 'replaced')",
            name="end_reason",
        ),
        sa.CheckConstraint("(ended_at IS NULL) = (end_reason IS NULL)", name="ended"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])


def downgrade() -> None:
    op.drop_table("sessions")
    op.drop_table("user_roles")
    op.drop_table("users")
