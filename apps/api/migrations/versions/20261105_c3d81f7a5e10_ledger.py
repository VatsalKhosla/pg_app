"""ledger

Revision ID: c3d81f7a5e10
Revises: b7e1c94d2f30
Create Date: 2026-11-05 22:00:00.000000

Double-entry books (step 6.4, ADR 0060). The database guards them itself: a transaction whose
entries don't balance is refused as it commits, and nothing posted can be changed or removed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d81f7a5e10"
down_revision: str | Sequence[str] | None = "b7e1c94d2f30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ledger_accounts",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
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
            "type IN ('asset', 'liability', 'revenue', 'expense')",
            name=op.f("ck_ledger_accounts_type"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ledger_accounts")),
        sa.UniqueConstraint("code", name=op.f("uq_ledger_accounts_code")),
    )
    op.create_table(
        "ledger_transactions",
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("booking_id", sa.BigInteger(), nullable=True),
        sa.Column("booking_code", sa.Text(), nullable=True),
        sa.Column("payment_id", sa.BigInteger(), nullable=True),
        sa.Column("memo", sa.Text(), server_default="", nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('token_received', 'token_refunded', 'owner_invoiced', 'token_applied')",
            name=op.f("ck_ledger_transactions_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["booking_id"], ["bookings.id"], name=op.f("fk_ledger_transactions_booking_id_bookings")
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"], ["payments.id"], name=op.f("fk_ledger_transactions_payment_id_payments")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ledger_transactions")),
        sa.UniqueConstraint("key", name=op.f("uq_ledger_transactions_key")),
        sa.UniqueConstraint("public_id", name=op.f("uq_ledger_transactions_public_id")),
    )
    op.create_index(
        "ix_ledger_transactions_booking_id", "ledger_transactions", ["booking_id"], unique=False
    )
    op.create_index(
        "ix_ledger_transactions_payment_id", "ledger_transactions", ["payment_id"], unique=False
    )
    op.create_index(
        "ix_ledger_transactions_booking_code", "ledger_transactions", ["booking_code"], unique=False
    )
    op.create_table(
        "ledger_entries",
        sa.Column("transaction_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "direction IN ('debit', 'credit')", name=op.f("ck_ledger_entries_direction")
        ),
        sa.CheckConstraint("amount_paise > 0", name=op.f("ck_ledger_entries_amount")),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["ledger_transactions.id"],
            name=op.f("fk_ledger_entries_transaction_id_ledger_transactions"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["ledger_accounts.id"],
            name=op.f("fk_ledger_entries_account_id_ledger_accounts"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ledger_entries")),
    )
    op.create_index(
        "ix_ledger_entries_transaction_id", "ledger_entries", ["transaction_id"], unique=False
    )
    op.create_index("ix_ledger_entries_account_id", "ledger_entries", ["account_id"], unique=False)
    op.execute(
        """
        CREATE FUNCTION ledger_refuse_change() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only: % refused', TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$
        """
    )
    for table in ("ledger_transactions", "ledger_entries"):
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table}"
            " FOR EACH ROW EXECUTE FUNCTION ledger_refuse_change()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table}"
            " FOR EACH STATEMENT EXECUTE FUNCTION ledger_refuse_change()"
        )
    op.execute(
        """
        CREATE FUNCTION ledger_transaction_balances() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            out_by bigint;
        BEGIN
            SELECT COALESCE(
                SUM(CASE direction WHEN 'debit' THEN amount_paise ELSE -amount_paise END), 0
            )
            INTO out_by FROM ledger_entries WHERE transaction_id = NEW.transaction_id;
            IF out_by <> 0 THEN
                RAISE EXCEPTION 'ledger transaction % is out by % paise', NEW.transaction_id, out_by
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER ledger_entries_balance AFTER INSERT ON ledger_entries"
        " DEFERRABLE INITIALLY DEFERRED"
        " FOR EACH ROW EXECUTE FUNCTION ledger_transaction_balances()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER ledger_entries_balance ON ledger_entries")
    op.execute("DROP FUNCTION ledger_transaction_balances()")
    for table in ("ledger_entries", "ledger_transactions"):
        op.execute(f"DROP TRIGGER {table}_no_truncate ON {table}")
        op.execute(f"DROP TRIGGER {table}_append_only ON {table}")
    op.execute("DROP FUNCTION ledger_refuse_change()")
    op.drop_index("ix_ledger_entries_account_id", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_transaction_id", table_name="ledger_entries")
    op.drop_table("ledger_entries")
    op.drop_index("ix_ledger_transactions_booking_code", table_name="ledger_transactions")
    op.drop_index("ix_ledger_transactions_payment_id", table_name="ledger_transactions")
    op.drop_index("ix_ledger_transactions_booking_id", table_name="ledger_transactions")
    op.drop_table("ledger_transactions")
    op.drop_table("ledger_accounts")
