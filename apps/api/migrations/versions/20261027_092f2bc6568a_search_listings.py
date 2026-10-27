"""search listings

Revision ID: 092f2bc6568a
Revises: 8d41f0c2b7e3
Create Date: 2026-10-27 18:45:00.000000

Search (step 3.2, ADR 0028): the search module's entry for each listing the public can find,
with public details only (the display point, never the exact one), indexed for where it is,
its amenities, and words or near misses in its name and locality. Price summaries gain their
room category's features, which search filters by (the migration before emptied them), and are
indexed by listing and month, as search looks them up.
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography
from sqlalchemy.dialects import postgresql

revision: str = "092f2bc6568a"
down_revision: str | Sequence[str] | None = "8d41f0c2b7e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[datetime]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "search_listings",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("property_id", sa.BigInteger(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("locality_id", sa.BigInteger(), nullable=False),
        sa.Column("locality_slug", sa.Text(), nullable=False),
        sa.Column("locality_name", sa.Text(), nullable=False),
        sa.Column(
            "display_location",
            Geography("POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("gender_policy", sa.Text(), nullable=False),
        sa.Column("meals", sa.Text(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("licensed", sa.Boolean(), nullable=False),
        sa.Column("amenities", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("media_ids", postgresql.ARRAY(sa.BigInteger()), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "search_text",
            sa.Text(),
            sa.Computed("name || ' '::text || locality_name", persisted=True),
            nullable=False,
        ),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('simple'::regconfig, name || ' '::text || locality_name)",
                persisted=True,
            ),
            nullable=False,
        ),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["properties.id"],
            name=op.f("fk_search_listings_property_id_properties"),
        ),
        sa.ForeignKeyConstraint(
            ["locality_id"],
            ["localities.id"],
            name=op.f("fk_search_listings_locality_id_localities"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_search_listings")),
        sa.UniqueConstraint("property_id", name=op.f("uq_search_listings_property_id")),
        sa.UniqueConstraint("public_id", name=op.f("uq_search_listings_public_id")),
    )
    op.create_index(
        "ix_search_listings_display_location",
        "search_listings",
        ["display_location"],
        postgresql_using="gist",
    )
    op.create_index("ix_search_listings_locality_id", "search_listings", ["locality_id"])
    op.create_index(
        "ix_search_listings_amenities", "search_listings", ["amenities"], postgresql_using="gin"
    )
    op.create_index(
        "ix_search_listings_search_vector",
        "search_listings",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_search_listings_search_text",
        "search_listings",
        ["search_text"],
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )
    op.create_index("ix_search_listings_published_at", "search_listings", ["published_at"])

    op.add_column("property_price_summaries", sa.Column("occupancy", sa.Text(), nullable=False))
    op.add_column("property_price_summaries", sa.Column("ac", sa.Boolean(), nullable=False))
    op.add_column(
        "property_price_summaries", sa.Column("attached_bath", sa.Boolean(), nullable=False)
    )
    op.create_check_constraint(
        op.f("ck_property_price_summaries_occupancy"),
        "property_price_summaries",
        "occupancy IN ('single', 'double', 'triple', 'quad')",
    )
    # Search looks up each listing's month (ADR 0028), which also serves replacing a listing's
    # summaries; the two indexes before are no longer needed.
    op.create_index(
        "ix_property_price_summaries_property_id_month",
        "property_price_summaries",
        ["property_id", "month"],
    )
    op.drop_index(
        "ix_property_price_summaries_month_min_rent_paise", table_name="property_price_summaries"
    )
    op.drop_index("ix_property_price_summaries_property_id", table_name="property_price_summaries")


def downgrade() -> None:
    op.create_index(
        "ix_property_price_summaries_property_id", "property_price_summaries", ["property_id"]
    )
    op.create_index(
        "ix_property_price_summaries_month_min_rent_paise",
        "property_price_summaries",
        ["month", "min_rent_paise"],
    )
    op.drop_index(
        "ix_property_price_summaries_property_id_month", table_name="property_price_summaries"
    )
    op.drop_constraint(
        op.f("ck_property_price_summaries_occupancy"), "property_price_summaries", type_="check"
    )
    op.drop_column("property_price_summaries", "attached_bath")
    op.drop_column("property_price_summaries", "ac")
    op.drop_column("property_price_summaries", "occupancy")
    op.drop_index("ix_search_listings_published_at", table_name="search_listings")
    op.drop_index("ix_search_listings_search_text", table_name="search_listings")
    op.drop_index("ix_search_listings_search_vector", table_name="search_listings")
    op.drop_index("ix_search_listings_amenities", table_name="search_listings")
    op.drop_index("ix_search_listings_locality_id", table_name="search_listings")
    op.drop_index("ix_search_listings_display_location", table_name="search_listings")
    op.drop_table("search_listings")
