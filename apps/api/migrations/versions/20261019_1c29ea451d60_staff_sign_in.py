"""staff sign-in

Revision ID: 1c29ea451d60
Revises: 5bdda56fa772
Create Date: 2026-10-19 17:08:02.413828

Staff sign-in of step 1.3 (ARCHITECTURE §6, §12). ``user_identities`` links a staff member's
Google account by its ``sub``, which is never reused, unlike addresses. ``totp_credentials`` holds
each staff member's authenticator app: only a salt, since the secret is derived from SECRET_KEY.
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "1c29ea451d60"
down_revision: str | Sequence[str] | None = "5bdda56fa772"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[datetime]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "user_identities",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("provider IN ('google')", name=op.f("ck_user_identities_provider")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_identities_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_identities")),
        sa.UniqueConstraint(
            "provider", "subject", name=op.f("uq_user_identities_provider_subject")
        ),
        sa.UniqueConstraint(
            "user_id", "provider", name=op.f("uq_user_identities_user_id_provider")
        ),
    )
    op.create_table(
        "totp_credentials",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("salt", sa.LargeBinary(length=16), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_step", sa.BigInteger(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("octet_length(salt) = 16", name=op.f("ck_totp_credentials_salt")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_totp_credentials_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_totp_credentials")),
        sa.UniqueConstraint("user_id", name=op.f("uq_totp_credentials_user_id")),
    )


def downgrade() -> None:
    op.drop_table("totp_credentials")
    op.drop_table("user_identities")
