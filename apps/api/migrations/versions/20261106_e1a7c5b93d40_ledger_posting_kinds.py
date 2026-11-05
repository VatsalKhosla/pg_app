"""ledger posting kinds

Revision ID: e1a7c5b93d40
Revises: d94e2b6c7f21
Create Date: 2026-11-06 10:00:00.000000

The postings steps 6.5 and 6.6 add: an owner paying their invoice's balance, or having it given
back, and what the gateway's settlement report says it kept, paid the bank and took back.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e1a7c5b93d40"
down_revision: str | Sequence[str] | None = "d94e2b6c7f21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BEFORE = ("token_received", "token_refunded", "owner_invoiced", "token_applied")
_AFTER = (
    *_BEFORE,
    "owner_paid",
    "owner_refunded",
    "gateway_fee",
    "settled",
    "refund_settled",
)


def _kinds(kinds: tuple[str, ...]) -> str:
    return "kind IN (" + ", ".join(f"'{kind}'" for kind in kinds) + ")"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_ledger_transactions_kind"), "ledger_transactions", type_="check")
    op.create_check_constraint(
        op.f("ck_ledger_transactions_kind"), "ledger_transactions", _kinds(_AFTER)
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_ledger_transactions_kind"), "ledger_transactions", type_="check")
    op.create_check_constraint(
        op.f("ck_ledger_transactions_kind"), "ledger_transactions", _kinds(_BEFORE)
    )
