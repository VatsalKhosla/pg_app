"""upi mandates

Revision ID: c6f2a8e4b9d1
Revises: b5e1d9c3a7f4
Create Date: 2026-11-06 13:00:00.000000

A token blocked by a UPI one-time mandate (step 6.7, ADR 0064): the gateway's customer and mandate,
how long the block lasts, and its debit; the two statuses a mandate's payment has of its own; and
what reconciliation raises about a mandate.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c6f2a8e4b9d1"
down_revision: str | Sequence[str] | None = "b5e1d9c3a7f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    sa.Column("provider_customer_id", sa.Text(), nullable=True),
    sa.Column("provider_mandate_id", sa.Text(), nullable=True),
    sa.Column("mandate_expires_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("provider_debit_order_id", sa.Text(), nullable=True),
    sa.Column("debit_amount_paise", sa.BigInteger(), nullable=True),
    sa.Column("debit_after", sa.DateTime(timezone=True), nullable=True),
)


def _replace(name: str, condition: str) -> None:
    op.drop_constraint(op.f(f"ck_payments_{name}"), "payments", type_="check")
    op.create_check_constraint(op.f(f"ck_payments_{name}"), "payments", condition)


_ISSUES_BEFORE = (
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
_ISSUES_AFTER = (*_ISSUES_BEFORE, "mandate_debit_failed", "mandate_cancelled")


def _issue_kinds(kinds: tuple[str, ...]) -> None:
    name = op.f("ck_reconciliation_issues_kind")
    op.drop_constraint(name, "reconciliation_issues", type_="check")
    op.create_check_constraint(
        name, "reconciliation_issues", "kind IN (" + ", ".join(f"'{k}'" for k in kinds) + ")"
    )


def upgrade() -> None:
    _issue_kinds(_ISSUES_AFTER)
    for column in _COLUMNS:
        op.add_column("payments", column)
    _replace("mode", "mode IN ('payment', 'upi_mandate')")
    _replace("status", "status IN ('created', 'authorized', 'captured', 'blocked', 'released')")
    _replace(
        "provider_payment",
        "status IN ('created', 'blocked', 'released') OR provider_payment_id IS NOT NULL",
    )
    op.create_check_constraint(
        op.f("ck_payments_mandate"),
        "payments",
        "mode = 'upi_mandate' OR (provider_customer_id IS NULL AND provider_mandate_id IS NULL"
        " AND provider_debit_order_id IS NULL AND status NOT IN ('blocked', 'released'))",
    )
    op.create_check_constraint(
        op.f("ck_payments_debit_amount"),
        "payments",
        "debit_amount_paise IS NULL OR (debit_amount_paise > 0"
        " AND debit_amount_paise <= amount_paise)",
    )
    op.create_index(
        "uq_payments_provider_mandate_id",
        "payments",
        ["provider", "provider_mandate_id"],
        unique=True,
        postgresql_where=sa.text("provider_mandate_id IS NOT NULL"),
    )
    op.create_index(
        "uq_payments_provider_debit_order_id",
        "payments",
        ["provider", "provider_debit_order_id"],
        unique=True,
        postgresql_where=sa.text("provider_debit_order_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_payments_provider_debit_order_id", table_name="payments")
    op.drop_index("uq_payments_provider_mandate_id", table_name="payments")
    op.drop_constraint(op.f("ck_payments_debit_amount"), "payments", type_="check")
    op.drop_constraint(op.f("ck_payments_mandate"), "payments", type_="check")
    # Mandates go with the columns that described them.
    _replace("provider_payment", "status = 'created' OR provider_payment_id IS NOT NULL")
    _replace("status", "status IN ('created', 'authorized', 'captured')")
    _replace("mode", "mode IN ('payment')")
    for column in reversed(_COLUMNS):
        op.drop_column("payments", column.name)
    _issue_kinds(_ISSUES_BEFORE)
