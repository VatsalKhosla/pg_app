"""grievances

Revision ID: 4c62184c0a3e
Revises: 564e32dc126d
Create Date: 2026-10-29 11:31:03.226014

Grievances (ADR 0034): complaints to the grievance officer with their ticket numbers, the
deadlines to acknowledge and resolve them, and the officer's reply and resolution.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4c62184c0a3e"
down_revision: str | Sequence[str] | None = "564e32dc126d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "grievances",
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("ticket_number", sa.Text(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("phone_e164", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("reference", sa.Text(), server_default="", nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledge_by", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolve_by", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.BigInteger(), nullable=True),
        sa.Column("reply", sa.Text(), server_default="", nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.BigInteger(), nullable=True),
        sa.Column("resolution", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'received') = (acknowledged_at IS NULL)"
            " AND (status <> 'acknowledged' OR reply <> '')",
            name=op.f("ck_grievances_acknowledged"),
        ),
        sa.CheckConstraint(
            "(status = 'resolved') = (resolved_at IS NOT NULL)"
            " AND (status <> 'resolved' OR resolution <> '')",
            name=op.f("ck_grievances_resolved"),
        ),
        sa.CheckConstraint(
            "category IN"
            " ('listing', 'visit', 'booking', 'owner', 'staff', 'privacy', 'account', 'other')",
            name=op.f("ck_grievances_category"),
        ),
        sa.CheckConstraint(
            "status IN ('received', 'acknowledged', 'resolved')", name=op.f("ck_grievances_status")
        ),
        sa.CheckConstraint(
            "char_length(name) <= 100 AND char_length(details) BETWEEN 1 AND 2000"
            " AND char_length(reference) <= 100 AND char_length(email) <= 254"
            " AND char_length(reply) <= 2000 AND char_length(resolution) <= 2000",
            name=op.f("ck_grievances_lengths"),
        ),
        sa.CheckConstraint(
            "phone_e164 IS NOT NULL OR email IS NOT NULL", name=op.f("ck_grievances_contact")
        ),
        sa.ForeignKeyConstraint(
            ["acknowledged_by"],
            ["users.id"],
            name=op.f("fk_grievances_acknowledged_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"],
            ["users.id"],
            name=op.f("fk_grievances_resolved_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_grievances_user_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grievances")),
        sa.UniqueConstraint("public_id", name=op.f("uq_grievances_public_id")),
        sa.UniqueConstraint("ticket_number", name=op.f("uq_grievances_ticket_number")),
    )
    op.create_index(
        "ix_grievances_status_received_at", "grievances", ["status", "received_at"], unique=False
    )
    op.create_index("ix_grievances_user_id", "grievances", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_grievances_user_id", table_name="grievances")
    op.drop_index("ix_grievances_status_received_at", table_name="grievances")
    op.drop_table("grievances")
