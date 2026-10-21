"""Geo tables (ARCHITECTURE §6): the reference data from data/places.json (ADR 0020).

Rows change only when the reference data is loaded (``python -m app.manage geo load``), never
through the API. Each keeps the OpenStreetMap element its coordinates came from (``osm_type``,
``osm_id``); stations and lines keep their Wikidata item as well. Coordinates are ``geography`` in
WGS 84, so distances come out in metres on the ground.
"""

from typing import Final

from geoalchemy2 import Geography, WKBElement
from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Model
from app.modules.geo.domain.places import SLUG_MAX_LENGTH, OsmType

SLUG_CHECK: Final = f"slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND char_length(slug) <= {SLUG_MAX_LENGTH}"
OSM_CHECK: Final = f"osm_type IN ({', '.join(f"'{kind}'" for kind in OsmType)}) AND osm_id > 0"
WIKIDATA_CHECK: Final = "wikidata_id ~ '^Q[1-9][0-9]*$'"


def _point() -> Geography:
    # Indexes are declared on each table, named like every other index.
    return Geography("POINT", srid=4326, spatial_index=False)


class ReferenceRow(Model):
    """A row of reference data: found by its slug, shown by its name."""

    __abstract__ = True

    slug: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)


class City(ReferenceRow):
    __tablename__ = "cities"

    center: Mapped[WKBElement] = mapped_column(_point())
    osm_type: Mapped[str] = mapped_column(Text)
    osm_id: Mapped[int] = mapped_column(BigInteger)

    __table_args__ = (
        CheckConstraint(SLUG_CHECK, name="slug"),
        CheckConstraint(OSM_CHECK, name="osm"),
    )


class Locality(ReferenceRow):
    """Where PGs are: the unit of `/pg-in/[locality]` and of rent bands."""

    __tablename__ = "localities"

    city_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("cities.id"))
    center: Mapped[WKBElement] = mapped_column(_point())
    # The locality's outline, when OpenStreetMap maps it as an area.
    boundary: Mapped[WKBElement | None] = mapped_column(
        Geography("MULTIPOLYGON", srid=4326, spatial_index=False)
    )
    osm_type: Mapped[str] = mapped_column(Text)
    osm_id: Mapped[int] = mapped_column(BigInteger)

    __table_args__ = (
        CheckConstraint(SLUG_CHECK, name="slug"),
        CheckConstraint(OSM_CHECK, name="osm"),
        Index("ix_localities_city_id", "city_id"),
        Index("ix_localities_center", "center", postgresql_using="gist"),
        Index("ix_localities_boundary", "boundary", postgresql_using="gist"),
        # Text search on locality names (ARCHITECTURE §6, §10.1).
        Index(
            "ix_localities_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )


class Campus(ReferenceRow):
    """What students search near: a college, or a university campus as a whole."""

    __tablename__ = "campuses"

    city_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("cities.id"))
    location: Mapped[WKBElement] = mapped_column(_point())
    osm_type: Mapped[str] = mapped_column(Text)
    osm_id: Mapped[int] = mapped_column(BigInteger)

    __table_args__ = (
        CheckConstraint(SLUG_CHECK, name="slug"),
        CheckConstraint(OSM_CHECK, name="osm"),
        Index("ix_campuses_city_id", "city_id"),
        Index("ix_campuses_location", "location", postgresql_using="gist"),
    )


class MetroLine(ReferenceRow):
    __tablename__ = "metro_lines"

    colour: Mapped[str] = mapped_column(Text)
    wikidata_id: Mapped[str] = mapped_column(Text, unique=True)

    __table_args__ = (
        CheckConstraint(SLUG_CHECK, name="slug"),
        CheckConstraint("colour ~ '^#[0-9A-F]{6}$'", name="colour"),
        CheckConstraint(WIKIDATA_CHECK, name="wikidata_id"),
    )


class MetroStation(ReferenceRow):
    __tablename__ = "metro_stations"

    location: Mapped[WKBElement] = mapped_column(_point())
    osm_type: Mapped[str] = mapped_column(Text)
    osm_id: Mapped[int] = mapped_column(BigInteger)
    wikidata_id: Mapped[str] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(SLUG_CHECK, name="slug"),
        CheckConstraint(OSM_CHECK, name="osm"),
        CheckConstraint(WIKIDATA_CHECK, name="wikidata_id"),
        Index("ix_metro_stations_location", "location", postgresql_using="gist"),
    )


class MetroStationLine(Model):
    """A line serving a station: an interchange has several."""

    __tablename__ = "metro_station_lines"

    station_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("metro_stations.id", ondelete="CASCADE")
    )
    line_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("metro_lines.id"))

    __table_args__ = (
        UniqueConstraint("station_id", "line_id"),
        Index("ix_metro_station_lines_line_id", "line_id"),
    )
