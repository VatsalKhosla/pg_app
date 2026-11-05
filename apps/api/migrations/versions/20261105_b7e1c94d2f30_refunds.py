"""refunds

Revision ID: b7e1c94d2f30
Revises: 8a4d3f0c1e22
Create Date: 2026-11-05 21:00:00.000000

Money given back (step 6.3, ADR 0059): one row per refund, whose key makes asking again find it. The
database itself refuses a second approval by the person who asked.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e1c94d2f30"
down_revision: str | Sequence[str] | None = "8a4d3f0c1e22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "refunds",
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("provider_refund_id", sa.Text(), nullable=True),
        sa.Column("reference", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.BigInteger(), nullable=True),
        sa.Column("approved_by", sa.BigInteger(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure", sa.Text(), nullable=True),
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
            "kind IN ('automatic', 'manual', 'gateway')", name=op.f("ck_refunds_kind")
        ),
        sa.CheckConstraint(
            "status IN ('awaiting_approval', 'requested', 'pending', 'processed', 'failed',"
            " 'declined')",
            name=op.f("ck_refunds_status"),
        ),
        sa.CheckConstraint("amount_paise > 0", name=op.f("ck_refunds_amount")),
        sa.CheckConstraint(
            "approved_by IS NULL OR approved_by <> requested_by",
            name=op.f("ck_refunds_two_people"),
        ),
        sa.CheckConstraint(
            "(status = 'processed') = (processed_at IS NOT NULL)", name=op.f("ck_refunds_processed")
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"], ["payments.id"], name=op.f("fk_refunds_payment_id_payments")
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"], ["users.id"], name=op.f("fk_refunds_requested_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"], ["users.id"], name=op.f("fk_refunds_approved_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refunds")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_refunds_idempotency_key")),
        sa.UniqueConstraint("public_id", name=op.f("uq_refunds_public_id")),
    )
    op.create_index("ix_refunds_payment_id", "refunds", ["payment_id"], unique=False)
    op.create_index("ix_refunds_requested_by", "refunds", ["requested_by"], unique=False)
    op.create_index("ix_refunds_approved_by", "refunds", ["approved_by"], unique=False)
    op.create_index("ix_refunds_status", "refunds", ["status", "public_id"], unique=False)
    op.create_index(
        "uq_refunds_provider_refund_id",
        "refunds",
        ["provider_refund_id"],
        unique=True,
        postgresql_where=sa.text("provider_refund_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_refunds_provider_refund_id",
        table_name="refunds",
        postgresql_where=sa.text("provider_refund_id IS NOT NULL"),
    )
    op.drop_index("ix_refunds_status", table_name="refunds")
    op.drop_index("ix_refunds_approved_by", table_name="refunds")
    op.drop_index("ix_refunds_requested_by", table_name="refunds")
    op.drop_index("ix_refunds_payment_id", table_name="refunds")
    op.drop_table("refunds")
