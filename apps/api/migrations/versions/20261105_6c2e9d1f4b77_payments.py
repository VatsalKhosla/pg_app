"""payments

Revision ID: 6c2e9d1f4b77
Revises: 3f8a6b5d2c71
Create Date: 2026-11-05 02:00:00.000000

Money asked for through a gateway (step 6.1, ADR 0056): one row per order, whose key makes asking
again find it. A gateway's order and payment ids are each unique to one row.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6c2e9d1f4b77"
down_revision: str | Sequence[str] | None = "3f8a6b5d2c71"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.BigInteger(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("provider_order_id", sa.Text(), nullable=True),
        sa.Column("provider_payment_id", sa.Text(), nullable=True),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), server_default="created", nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("purpose IN ('token')", name=op.f("ck_payments_purpose")),
        sa.CheckConstraint("mode IN ('payment')", name=op.f("ck_payments_mode")),
        sa.CheckConstraint(
            "status IN ('created', 'authorized', 'captured')", name=op.f("ck_payments_status")
        ),
        sa.CheckConstraint("amount_paise > 0", name=op.f("ck_payments_amount")),
        sa.CheckConstraint(
            "(status = 'captured') = (captured_at IS NOT NULL)", name=op.f("ck_payments_captured")
        ),
        sa.CheckConstraint(
            "status = 'created' OR provider_payment_id IS NOT NULL",
            name=op.f("ck_payments_provider_payment"),
        ),
        sa.ForeignKeyConstraint(
            ["booking_id"], ["bookings.id"], name=op.f("fk_payments_booking_id_bookings")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_payments_idempotency_key")),
        sa.UniqueConstraint("public_id", name=op.f("uq_payments_public_id")),
    )
    op.create_index("ix_payments_booking_id", "payments", ["booking_id"], unique=False)
    op.create_index(
        "uq_payments_provider_order_id",
        "payments",
        ["provider", "provider_order_id"],
        unique=True,
        postgresql_where=sa.text("provider_order_id IS NOT NULL"),
    )
    op.create_index(
        "uq_payments_provider_payment_id",
        "payments",
        ["provider", "provider_payment_id"],
        unique=True,
        postgresql_where=sa.text("provider_payment_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_payments_provider_payment_id",
        table_name="payments",
        postgresql_where=sa.text("provider_payment_id IS NOT NULL"),
    )
    op.drop_index(
        "uq_payments_provider_order_id",
        table_name="payments",
        postgresql_where=sa.text("provider_order_id IS NOT NULL"),
    )
    op.drop_index("ix_payments_booking_id", table_name="payments")
    op.drop_table("payments")
