"""fill the price summaries

Revision ID: 5c2e9b1d7a40
Revises: 1aec74b70c66
Create Date: 2026-10-27 15:20:00.000000

A data migration, kept apart from the schema migration (backend rules): listings that exist
before step 3.1 get their price summaries as soon as the worker runs, rather than at the first
nightly refresh. It queues the nightly job once (ADR 0027); the job kind is written out here so
this migration means the same thing however the search module changes later.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "5c2e9b1d7a40"
down_revision: str | Sequence[str] | None = "1aec74b70c66"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEDUPE_KEY = "search.fill_price_summaries:5c2e9b1d7a40"

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
    op.execute(
        postgresql.insert(outbox_jobs)
        .values(
            kind="search.recompute_all_price_summaries",
            payload={},
            max_attempts=10,
            run_at=sa.func.now(),
            dedupe_key=DEDUPE_KEY,
        )
        .on_conflict_do_nothing(
            index_elements=["dedupe_key"], index_where=sa.text("dedupe_key IS NOT NULL")
        )
    )


def downgrade() -> None:
    op.execute(
        outbox_jobs.delete().where(
            outbox_jobs.c.dedupe_key == DEDUPE_KEY, outbox_jobs.c.status == "pending"
        )
    )
