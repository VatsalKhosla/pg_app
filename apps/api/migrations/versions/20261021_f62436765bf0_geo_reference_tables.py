"""geo reference tables

Revision ID: f62436765bf0
Revises: 01d405b87985
Create Date: 2026-10-21 21:13:22.850089

The geo reference data of step 2.1 (ARCHITECTURE §6, ADR 0020):
- cities, with their localities and campuses;
- metro lines, metro stations, and which lines serve each station.

Coordinates are ``geography`` in WGS 84, with GiST indexes for distance queries. Each row keeps
the OpenStreetMap element it came from; lines and stations also keep their Wikidata item. The rows
come from ``python -m app.manage geo load``, a separate step, so this migration holds no data.
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography
from sqlalchemy.schema import SchemaItem

revision: str = "f62436765bf0"
down_revision: str | Sequence[str] | None = "01d405b87985"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SLUG_CHECK = "slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND char_length(slug) <= 64"
OSM_CHECK = "osm_type IN ('node', 'way', 'relation') AND osm_id > 0"
WIKIDATA_CHECK = "wikidata_id ~ '^Q[1-9][0-9]*$'"


def _timestamps() -> list[sa.Column[datetime]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _geography(name: str, kind: str, *, nullable: bool = False) -> sa.Column[object]:
    return sa.Column(name, Geography(kind, srid=4326, spatial_index=False), nullable=nullable)


def _slug_and_osm(table: str) -> list[SchemaItem]:
    return [
        sa.Column("osm_type", sa.Text(), nullable=False),
        sa.Column("osm_id", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(SLUG_CHECK, name=op.f(f"ck_{table}_slug")),
        sa.CheckConstraint(OSM_CHECK, name=op.f(f"ck_{table}_osm")),
    ]


def upgrade() -> None:
    op.create_table(
        "cities",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        _geography("center", "POINT"),
        *_slug_and_osm("cities"),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cities")),
        sa.UniqueConstraint("slug", name=op.f("uq_cities_slug")),
    )
    op.create_table(
        "localities",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("city_id", sa.BigInteger(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        _geography("center", "POINT"),
        _geography("boundary", "MULTIPOLYGON", nullable=True),
        *_slug_and_osm("localities"),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["city_id"], ["cities.id"], name=op.f("fk_localities_city_id_cities")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_localities")),
        sa.UniqueConstraint("slug", name=op.f("uq_localities_slug")),
    )
    op.create_index("ix_localities_city_id", "localities", ["city_id"])
    op.create_index("ix_localities_center", "localities", ["center"], postgresql_using="gist")
    op.create_index("ix_localities_boundary", "localities", ["boundary"], postgresql_using="gist")
    op.create_index(
        "ix_localities_name_trgm",
        "localities",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_table(
        "campuses",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("city_id", sa.BigInteger(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        _geography("location", "POINT"),
        *_slug_and_osm("campuses"),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["city_id"], ["cities.id"], name=op.f("fk_campuses_city_id_cities")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_campuses")),
        sa.UniqueConstraint("slug", name=op.f("uq_campuses_slug")),
    )
    op.create_index("ix_campuses_city_id", "campuses", ["city_id"])
    op.create_index("ix_campuses_location", "campuses", ["location"], postgresql_using="gist")
    op.create_table(
        "metro_lines",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("colour", sa.Text(), nullable=False),
        sa.Column("wikidata_id", sa.Text(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(SLUG_CHECK, name=op.f("ck_metro_lines_slug")),
        sa.CheckConstraint("colour ~ '^#[0-9A-F]{6}$'", name=op.f("ck_metro_lines_colour")),
        sa.CheckConstraint(WIKIDATA_CHECK, name=op.f("ck_metro_lines_wikidata_id")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metro_lines")),
        sa.UniqueConstraint("slug", name=op.f("uq_metro_lines_slug")),
        sa.UniqueConstraint("wikidata_id", name=op.f("uq_metro_lines_wikidata_id")),
    )
    op.create_table(
        "metro_stations",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        _geography("location", "POINT"),
        sa.Column("wikidata_id", sa.Text(), nullable=False),
        *_slug_and_osm("metro_stations"),
        *_timestamps(),
        sa.CheckConstraint(WIKIDATA_CHECK, name=op.f("ck_metro_stations_wikidata_id")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metro_stations")),
        sa.UniqueConstraint("slug", name=op.f("uq_metro_stations_slug")),
    )
    op.create_index(
        "ix_metro_stations_location", "metro_stations", ["location"], postgresql_using="gist"
    )
    op.create_table(
        "metro_station_lines",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("station_id", sa.BigInteger(), nullable=False),
        sa.Column("line_id", sa.BigInteger(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["station_id"],
            ["metro_stations.id"],
            name=op.f("fk_metro_station_lines_station_id_metro_stations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["line_id"], ["metro_lines.id"], name=op.f("fk_metro_station_lines_line_id_metro_lines")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metro_station_lines")),
        sa.UniqueConstraint(
            "station_id", "line_id", name=op.f("uq_metro_station_lines_station_id_line_id")
        ),
    )
    op.create_index("ix_metro_station_lines_line_id", "metro_station_lines", ["line_id"])


def downgrade() -> None:
    op.drop_table("metro_station_lines")
    op.drop_table("metro_stations")
    op.drop_table("metro_lines")
    op.drop_table("campuses")
    op.drop_table("localities")
    op.drop_table("cities")
