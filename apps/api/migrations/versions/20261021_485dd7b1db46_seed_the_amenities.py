"""seed the amenities

Revision ID: 485dd7b1db46
Revises: dcab8b9533e2
Create Date: 2026-10-21 21:47:19.580760

The amenities a listing can have (step 2.2, ADR 0021). Search filters on their slugs
(ARCHITECTURE §10.1), so slugs never change once used; names may. What a room itself has (AC, an
attached bath, a balcony) belongs to its room category, and meals to the property, not here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "485dd7b1db46"
down_revision: str | Sequence[str] | None = "dcab8b9533e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AMENITIES: list[tuple[str, str]] = [
    ("wifi", "Wi-Fi"),
    ("power-backup", "Power backup"),
    ("ro-water", "RO drinking water"),
    ("hot-water", "Hot water"),
    ("laundry", "Laundry"),
    ("housekeeping", "Housekeeping"),
    ("cctv", "CCTV"),
    ("warden", "Warden"),
    ("secure-entry", "Biometric or card entry"),
    ("lift", "Lift"),
    ("parking", "Parking"),
    ("common-room", "Common room"),
    ("study-area", "Study area"),
    ("refrigerator", "Refrigerator"),
    ("gym", "Gym"),
]

amenities = sa.table("amenities", sa.column("slug", sa.Text()), sa.column("name", sa.Text()))


def upgrade() -> None:
    op.bulk_insert(amenities, [{"slug": slug, "name": name} for slug, name in AMENITIES])


def downgrade() -> None:
    op.execute(amenities.delete().where(amenities.c.slug.in_([slug for slug, _ in AMENITIES])))
