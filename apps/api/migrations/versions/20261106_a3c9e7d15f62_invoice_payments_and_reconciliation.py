"""invoice payments and reconciliation

Revision ID: a3c9e7d15f62
Revises: f2b8d6c04e51
Create Date: 2026-11-06 10:02:00.000000

Payments learn to pay an owner's invoice through a payment link (step 6.5, ADR 0061), and when
each was asked for, by the app's clock; reconciliation keeps what it finds for ops (step 6.6, ADR
0062).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3c9e7d15f62"
down_revision: str | Sequence[str] | None = "f2b8d6c04e51"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ISSUE_KINDS = (
    "unknown_payment",
    "unknown_refund",
    "amount_mismatch",
    "not_captured_here",
    "refund_not_processed_here",
    "unexpected_item",
    "not_settled",
    "stuck_authorized",
    "refund_stuck",
    "link_mismatch",
)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_payments_purpose"), "payments", type_="check")
    op.create_check_constraint(
        op.f("ck_payments_purpose"), "payments", "purpose IN ('token', 'owner_invoice')"
    )
    op.add_column("payments", sa.Column("made_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("payments", sa.Column("invoice_id", sa.BigInteger(), nullable=True))
    op.add_column("payments", sa.Column("provider_link_id", sa.Text(), nullable=True))
    op.add_column("payments", sa.Column("link_ended_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        op.f("fk_payments_invoice_id_owner_invoices"),
        "payments",
        "owner_invoices",
        ["invoice_id"],
        ["id"],
    )
    op.create_check_constraint(
        op.f("ck_payments_invoice"),
        "payments",
        "(purpose = 'owner_invoice') = (invoice_id IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_payments_link"),
        "payments",
        "provider_link_id IS NULL OR purpose = 'owner_invoice'",
    )
    op.create_index("ix_payments_invoice_id", "payments", ["invoice_id"], unique=False)
    op.create_index(
        "uq_payments_provider_link_id",
        "payments",
        ["provider", "provider_link_id"],
        unique=True,
        postgresql_where=sa.text("provider_link_id IS NOT NULL"),
    )
    op.create_index(
        "uq_payments_open_invoice_link",
        "payments",
        ["invoice_id"],
        unique=True,
        postgresql_where=sa.text("invoice_id IS NOT NULL AND link_ended_at IS NULL"),
    )
    op.create_index("ix_payments_status_made_at", "payments", ["status", "made_at"], unique=False)
    op.create_table(
        "reconciliation_issues",
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("reference", sa.Text(), nullable=False),
        sa.Column("booking_code", sa.Text(), nullable=True),
        sa.Column("amount_paise", sa.BigInteger(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("found_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.BigInteger(), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
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
            "kind IN (" + ", ".join(f"'{kind}'" for kind in _ISSUE_KINDS) + ")",
            name=op.f("ck_reconciliation_issues_kind"),
        ),
        sa.CheckConstraint(
            "(resolved_at IS NULL) = (resolved_by IS NULL)"
            " AND (resolved_at IS NULL) = (resolution IS NULL)",
            name=op.f("ck_reconciliation_issues_resolved"),
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"], ["users.id"], name=op.f("fk_reconciliation_issues_resolved_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reconciliation_issues")),
        sa.UniqueConstraint("public_id", name=op.f("uq_reconciliation_issues_public_id")),
        sa.UniqueConstraint(
            "kind", "provider", "reference", name="uq_reconciliation_issues_kind_reference"
        ),
    )
    op.create_index(
        "ix_reconciliation_issues_resolved_at",
        "reconciliation_issues",
        ["resolved_at", "public_id"],
        unique=False,
    )
    op.create_index(
        "ix_reconciliation_issues_resolved_by",
        "reconciliation_issues",
        ["resolved_by"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_reconciliation_issues_resolved_by", table_name="reconciliation_issues")
    op.drop_index("ix_reconciliation_issues_resolved_at", table_name="reconciliation_issues")
    op.drop_table("reconciliation_issues")
    op.drop_index("ix_payments_status_made_at", table_name="payments")
    op.drop_index("uq_payments_open_invoice_link", table_name="payments")
    op.drop_index("uq_payments_provider_link_id", table_name="payments")
    op.drop_index("ix_payments_invoice_id", table_name="payments")
    op.drop_constraint(op.f("ck_payments_link"), "payments", type_="check")
    op.drop_constraint(op.f("ck_payments_invoice"), "payments", type_="check")
    op.drop_constraint(
        op.f("fk_payments_invoice_id_owner_invoices"), "payments", type_="foreignkey"
    )
    op.drop_column("payments", "link_ended_at")
    op.drop_column("payments", "provider_link_id")
    op.drop_column("payments", "invoice_id")
    op.drop_column("payments", "made_at")
    # Payments of invoices go with the column that says which invoice.
    op.drop_constraint(op.f("ck_payments_purpose"), "payments", type_="check")
    op.create_check_constraint(op.f("ck_payments_purpose"), "payments", "purpose IN ('token')")
