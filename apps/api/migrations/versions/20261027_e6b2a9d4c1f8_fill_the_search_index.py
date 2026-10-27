"""fill the search index

Revision ID: e6b2a9d4c1f8
Revises: 092f2bc6568a
Create Date: 2026-10-27 18:50:00.000000

A data migration, kept apart from the schema migration (backend rules): every listing that
exists gets its search entry and price summaries as soon as the worker runs, by queueing the
nightly refresh once (ADR 0028). The job kind is written out here so this migration means the
same thing however the search module changes later.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e6b2a9d4c1f8"
down_revision: str | Sequence[str] | None = "092f2bc6568a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEDUPE_KEY = "search.fill_search_index:e6b2a9d4c1f8"

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
            kind="search.refresh_all",
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
