"""seed ledger accounts

Revision ID: d94e2b6c7f21
Revises: c3d81f7a5e10
Create Date: 2026-11-05 22:01:00.000000

The chart of accounts (ARCHITECTURE §9.4). The rows are written out here, because a migration has to
keep meaning what it meant, whatever the code says later. A test holds them to the code's chart.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d94e2b6c7f21"
down_revision: str | Sequence[str] | None = "c3d81f7a5e10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACCOUNTS = sa.table(
    "ledger_accounts",
    sa.column("code", sa.Text),
    sa.column("name", sa.Text),
    sa.column("type", sa.Text),
)


def upgrade() -> None:
    op.bulk_insert(
        _ACCOUNTS,
        [
            {"code": "gateway_clearing", "name": "Gateway clearing", "type": "asset"},
            {"code": "bank", "name": "Bank", "type": "asset"},
            {"code": "owner_receivable", "name": "Owed by owners", "type": "asset"},
            {"code": "student_tokens_held", "name": "Students' tokens held", "type": "liability"},
            {"code": "owner_payable", "name": "Owed to owners", "type": "liability"},
            {"code": "gst_payable", "name": "GST payable", "type": "liability"},
            {"code": "placement_fee_revenue", "name": "Placement fees", "type": "revenue"},
            {"code": "payment_fees", "name": "Payment gateway fees", "type": "expense"},
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM ledger_accounts")
