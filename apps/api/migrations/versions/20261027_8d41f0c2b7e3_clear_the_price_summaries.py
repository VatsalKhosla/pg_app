"""clear the price summaries

Revision ID: 8d41f0c2b7e3
Revises: 5c2e9b1d7a40
Create Date: 2026-10-27 18:40:00.000000

A data migration, kept apart from the schema migration after it (backend rules). Step 3.2 gives
each price summary its room category's features, so the summaries are emptied first; they are
derived from the catalog, and the migration after next has them worked out again. Jobs waiting
under step 3.1's names, which step 3.2 renames, are dropped rather than left to fail (ADR 0028).
Downgrading queues step 3.1's refresh, which fills them the old way.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8d41f0c2b7e3"
down_revision: str | Sequence[str] | None = "5c2e9b1d7a40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RENAMED = ("search.recompute_price_summaries", "search.recompute_all_price_summaries")

summaries = sa.table("property_price_summaries")
outbox_jobs = sa.table(
    "outbox_jobs",
    sa.column("kind", sa.Text()),
    sa.column("payload", postgresql.JSONB()),
    sa.column("status", sa.Text()),
    sa.column("max_attempts", sa.Integer()),
    sa.column("run_at", sa.DateTime(timezone=True)),
    sa.column("dedupe_key", sa.Text()),
)


def upgrade() -> None:
    op.execute(summaries.delete())
    op.execute(
        outbox_jobs.delete().where(
            outbox_jobs.c.kind.in_(RENAMED), outbox_jobs.c.status == "pending"
        )
    )


def downgrade() -> None:
    op.execute(
        postgresql.insert(outbox_jobs)
        .values(
            kind="search.recompute_all_price_summaries",
            payload={},
            max_attempts=10,
            run_at=sa.func.now(),
            dedupe_key="search.fill_price_summaries:8d41f0c2b7e3",
        )
        .on_conflict_do_nothing(
            index_elements=["dedupe_key"], index_where=sa.text("dedupe_key IS NOT NULL")
        )
    )
