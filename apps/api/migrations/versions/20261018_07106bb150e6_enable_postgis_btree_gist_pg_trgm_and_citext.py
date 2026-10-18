"""enable postgis, btree_gist, pg_trgm and citext

Revision ID: 07106bb150e6
Revises:
Create Date: 2026-10-18 21:05:09.731954

PostGIS for locations and distances, btree_gist for the inventory exclusion constraint (the
double-booking guarantee), pg_trgm for fuzzy search and citext for case-insensitive emails
(ARCHITECTURE §6). On RDS this needs the rds_superuser role, which the migration role has.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "07106bb150e6"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS citext")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
    op.execute("DROP EXTENSION IF EXISTS postgis")
