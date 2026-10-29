"""seed pricing policy defaults

Revision ID: c60c5641d497
Revises: ce5d7b09e10b
Create Date: 2026-10-29 13:05:54.327963

A data migration, kept apart from the schema migration (backend rules): the first version of each
policy, from PRODUCT_CONTEXT §9 (ADR 0036). The values are written out here, so this migration
means the same thing however the code changes later; admins change them from then on. In force
from the start of 2026, before anything could be priced. No rent band is seeded: none is official
yet, and internal ones are ops' to set.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "c60c5641d497"
down_revision: str | Sequence[str] | None = "ce5d7b09e10b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SINCE = datetime(2026, 1, 1, tzinfo=UTC)
NOTE = "The defaults in PRODUCT_CONTEXT §9."

POLICIES: dict[str, dict[str, int | str]] = {
    # Rules 2 and 3: 30% of the listed rent, GST at 18% added until the founders decide.
    "fee_policies": {
        "rate_bps": 3_000,
        "basis": "listed_rent",
        "gst_rate_bps": 1_800,
        "gst_mode": "exclusive",
    },
    # Rules 8 and 9: a ₹2,000 token, free cancellation up to 7 days before moving in, refunds in
    # full after that until Razorpay Route can pay an owner.
    "booking_policies": {
        "token_paise": 200_000,
        "hold_minutes": 15,
        "free_cancel_days": 7,
        "check_window_hours": 24,
        "confirm_deadline_hours": 12,
        "no_show_days": 3,
        "late_cancel_policy": "refund_full",
        "max_active_holds_per_user": 1,
        "max_advance_days": 120,
    },
    # Rule 6: a premium of 40% and a discount of 30% at most, rounded to ₹50.
    "pricing_caps": {
        "max_premium_bps": 4_000,
        "max_discount_bps": 3_000,
        "rounding_step_paise": 5_000,
    },
}


def _table(name: str, values: dict[str, int | str]) -> sa.TableClause:
    return sa.table(
        name,
        sa.column("public_id", sa.Uuid()),
        sa.column("effective_from", sa.DateTime(timezone=True)),
        sa.column("note", sa.Text()),
        *(sa.column(column) for column in values),
    )


def upgrade() -> None:
    for name, values in POLICIES.items():
        op.bulk_insert(
            _table(name, values),
            [{"public_id": uuid.uuid7(), "effective_from": SINCE, "note": NOTE, **values}],
        )


def downgrade() -> None:
    for name, values in POLICIES.items():
        table = _table(name, values)
        op.execute(table.delete().where(table.c.note == NOTE))
