"""consents and data requests

Revision ID: 69809c8a071a
Revises: 1c29ea451d60
Create Date: 2026-10-19 21:46:52.120132

Consent and data requests of step 1.5 (ARCHITECTURE §6, §12; DPDP). ``consents`` keeps every grant
and withdrawal, per purpose and privacy notice version, with one active consent per purpose and
version. ``data_requests`` allows one open request of each kind per person; ``data_exports`` holds
an export's JSON file until the retention job deletes it.
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "69809c8a071a"
down_revision: str | Sequence[str] | None = "1c29ea451d60"
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
        "consents",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("notice_version", sa.Text(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("purpose IN ('account', 'marketing')", name=op.f("ck_consents_purpose")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_consents_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consents")),
    )
    op.create_index("ix_consents_user_id", "consents", ["user_id"])
    op.create_index(
        "uq_consents_active",
        "consents",
        ["user_id", "purpose", "notice_version"],
        unique=True,
        postgresql_where=sa.text("withdrawn_at IS NULL"),
    )
    op.create_table(
        "data_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.BigInteger(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("kind IN ('export', 'deletion')", name=op.f("ck_data_requests_kind")),
        sa.CheckConstraint(
            "status IN ('received', 'ready', 'expired', 'completed', 'rejected')",
            name=op.f("ck_data_requests_status"),
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"],
            ["users.id"],
            name=op.f("fk_data_requests_resolved_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_data_requests_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_requests")),
        sa.UniqueConstraint("public_id", name=op.f("uq_data_requests_public_id")),
    )
    op.create_index("ix_data_requests_user_id", "data_requests", ["user_id"])
    op.create_index(
        "ix_data_requests_status_requested_at", "data_requests", ["status", "requested_at"]
    )
    op.create_index(
        "uq_data_requests_open",
        "data_requests",
        ["user_id", "kind"],
        unique=True,
        postgresql_where=sa.text("status = 'received'"),
    )
    op.create_table(
        "data_exports",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("data_request_id", sa.BigInteger(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["data_request_id"],
            ["data_requests.id"],
            name=op.f("fk_data_exports_data_request_id_data_requests"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_exports")),
        sa.UniqueConstraint("data_request_id", name=op.f("uq_data_exports_data_request_id")),
    )


def downgrade() -> None:
    op.drop_table("data_exports")
    op.drop_table("data_requests")
    op.drop_table("consents")
