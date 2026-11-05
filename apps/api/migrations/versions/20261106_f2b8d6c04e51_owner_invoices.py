"""owner invoices

Revision ID: f2b8d6c04e51
Revises: e1a7c5b93d40
Create Date: 2026-11-06 10:01:00.000000

Owners' invoices (step 6.5, ADR 0061), numbered without gaps per financial year. The database
keeps an invoice as issued: a trigger refuses any change to its number or amounts, and refuses
removing one.
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "f2b8d6c04e51"
down_revision: str | Sequence[str] | None = "e1a7c5b93d40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# What an issued invoice says, which never changes.
_FIXED = (
    "public_id",
    "owner_id",
    "booking_id",
    "property_id",
    "booking_code",
    "financial_year",
    "serial",
    "number",
    "base_rent_paise",
    "fee_rate_bps",
    "gst_rate_bps",
    "gst_included",
    "fee_paise",
    "gst_paise",
    "total_paise",
    "token_applied_paise",
    "token_over_paise",
    "balance_due_paise",
    "issued_at",
)


def _stamps() -> list[sa.Column[Any]]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "invoice_sequences",
        sa.Column("financial_year", sa.Text(), nullable=False),
        sa.Column("last_serial", sa.Integer(), nullable=False),
        *_stamps(),
        sa.CheckConstraint("last_serial > 0", name=op.f("ck_invoice_sequences_last_serial")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoice_sequences")),
        sa.UniqueConstraint("financial_year", name=op.f("uq_invoice_sequences_financial_year")),
    )
    op.create_table(
        "owner_invoices",
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("booking_id", sa.BigInteger(), nullable=False),
        sa.Column("property_id", sa.BigInteger(), nullable=False),
        sa.Column("booking_code", sa.Text(), nullable=False),
        sa.Column("financial_year", sa.Text(), nullable=False),
        sa.Column("serial", sa.Integer(), nullable=False),
        sa.Column("number", sa.Text(), nullable=False),
        sa.Column("base_rent_paise", sa.BigInteger(), nullable=False),
        sa.Column("fee_rate_bps", sa.Integer(), nullable=False),
        sa.Column("gst_rate_bps", sa.Integer(), nullable=False),
        sa.Column("gst_included", sa.Boolean(), nullable=False),
        sa.Column("fee_paise", sa.BigInteger(), nullable=False),
        sa.Column("gst_paise", sa.BigInteger(), nullable=False),
        sa.Column("total_paise", sa.BigInteger(), nullable=False),
        sa.Column("token_applied_paise", sa.BigInteger(), nullable=False),
        sa.Column("token_over_paise", sa.BigInteger(), nullable=False),
        sa.Column("balance_due_paise", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pdf_key", sa.Text(), nullable=True),
        sa.Column("pay_provider", sa.Text(), nullable=True),
        sa.Column("pay_url", sa.Text(), nullable=True),
        *_stamps(),
        sa.CheckConstraint("status IN ('issued', 'paid')", name=op.f("ck_owner_invoices_status")),
        sa.CheckConstraint(
            "base_rent_paise > 0 AND fee_paise > 0 AND gst_paise >= 0"
            " AND token_applied_paise >= 0 AND token_over_paise >= 0 AND balance_due_paise >= 0"
            " AND fee_rate_bps > 0 AND gst_rate_bps >= 0 AND serial > 0",
            name=op.f("ck_owner_invoices_amounts"),
        ),
        sa.CheckConstraint(
            "total_paise = fee_paise + gst_paise", name=op.f("ck_owner_invoices_total")
        ),
        sa.CheckConstraint(
            "balance_due_paise = total_paise - token_applied_paise",
            name=op.f("ck_owner_invoices_balance"),
        ),
        sa.CheckConstraint(
            "token_over_paise = 0 OR balance_due_paise = 0",
            name=op.f("ck_owner_invoices_token_over"),
        ),
        sa.CheckConstraint(
            "(status = 'paid') = (paid_at IS NOT NULL)", name=op.f("ck_owner_invoices_paid")
        ),
        sa.CheckConstraint(
            "(pay_url IS NULL) = (pay_provider IS NULL)", name=op.f("ck_owner_invoices_pay")
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["owners.id"], name=op.f("fk_owner_invoices_owner_id_owners")
        ),
        sa.ForeignKeyConstraint(
            ["booking_id"], ["bookings.id"], name=op.f("fk_owner_invoices_booking_id_bookings")
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["properties.id"],
            name=op.f("fk_owner_invoices_property_id_properties"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_owner_invoices")),
        sa.UniqueConstraint("booking_id", name=op.f("uq_owner_invoices_booking_id")),
        sa.UniqueConstraint("number", name=op.f("uq_owner_invoices_number")),
        sa.UniqueConstraint("public_id", name=op.f("uq_owner_invoices_public_id")),
        sa.UniqueConstraint("financial_year", "serial", name="uq_owner_invoices_serial"),
    )
    op.create_index(
        "ix_owner_invoices_owner_id", "owner_invoices", ["owner_id", "public_id"], unique=False
    )
    op.create_index(
        "ix_owner_invoices_property_id", "owner_invoices", ["property_id"], unique=False
    )
    op.create_index(
        "ix_owner_invoices_status", "owner_invoices", ["status", "public_id"], unique=False
    )
    op.create_index(
        "ix_owner_invoices_booking_code", "owner_invoices", ["booking_code"], unique=False
    )
    changed = " OR ".join(f"NEW.{column} IS DISTINCT FROM OLD.{column}" for column in _FIXED)
    op.execute(
        f"""
        CREATE FUNCTION owner_invoice_as_issued() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                IF NOT ({changed}) THEN
                    RETURN NEW;
                END IF;
            END IF;
            RAISE EXCEPTION 'an issued invoice stays as issued: % refused', TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER owner_invoices_as_issued BEFORE UPDATE OR DELETE ON owner_invoices"
        " FOR EACH ROW EXECUTE FUNCTION owner_invoice_as_issued()"
    )
    op.execute(
        "CREATE TRIGGER owner_invoices_no_truncate BEFORE TRUNCATE ON owner_invoices"
        " FOR EACH STATEMENT EXECUTE FUNCTION owner_invoice_as_issued()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER owner_invoices_no_truncate ON owner_invoices")
    op.execute("DROP TRIGGER owner_invoices_as_issued ON owner_invoices")
    op.execute("DROP FUNCTION owner_invoice_as_issued()")
    op.drop_index("ix_owner_invoices_booking_code", table_name="owner_invoices")
    op.drop_index("ix_owner_invoices_status", table_name="owner_invoices")
    op.drop_index("ix_owner_invoices_property_id", table_name="owner_invoices")
    op.drop_index("ix_owner_invoices_owner_id", table_name="owner_invoices")
    op.drop_table("owner_invoices")
    op.drop_table("invoice_sequences")
