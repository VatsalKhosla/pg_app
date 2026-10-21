"""PostGIS from SQLAlchemy: geography values in, and coordinates and distances out.

Columns are ``geography`` in WGS 84 (GeoAlchemy2 types), so distances are metres on the
ellipsoid. Values go in as WKT and come out through ST_Y and ST_X, so no geometry library is
needed.
"""

from typing import TYPE_CHECKING, Final

from geoalchemy2 import Geometry, WKTElement
from sqlalchemy import ColumnElement, Float, SQLColumnExpression, cast, func

if TYPE_CHECKING:
    from collections.abc import Iterable

    from app.core.geometry import Point

# ST_X and ST_Y read geometry, not geography.
_GEOMETRY: Final = Geometry(geometry_type=None)


def point_wkt(point: Point) -> WKTElement:
    return WKTElement(f"POINT({point.lng!r} {point.lat!r})", srid=4326)


def multipolygon_wkt(polygons: Iterable[Iterable[Iterable[tuple[float, float]]]]) -> WKTElement:
    """A MultiPolygon from GeoJSON-ordered positions (longitude, latitude)."""

    def ring(positions: Iterable[tuple[float, float]]) -> str:
        return "(" + ", ".join(f"{lng!r} {lat!r}" for lng, lat in positions) + ")"

    def polygon(rings: Iterable[Iterable[tuple[float, float]]]) -> str:
        return "(" + ", ".join(ring(each) for each in rings) + ")"

    return WKTElement(
        "MULTIPOLYGON(" + ", ".join(polygon(each) for each in polygons) + ")", srid=4326
    )


def geography(point: Point) -> ColumnElement[object]:
    """A point as a geography value in a query, to compare with geography columns."""
    return func.ST_GeogFromText(f"SRID=4326;POINT({point.lng!r} {point.lat!r})")


def lat(column: SQLColumnExpression[object]) -> ColumnElement[float]:
    return func.ST_Y(cast(column, _GEOMETRY), type_=Float)


def lng(column: SQLColumnExpression[object]) -> ColumnElement[float]:
    return func.ST_X(cast(column, _GEOMETRY), type_=Float)


def distance(
    a: SQLColumnExpression[object], b: SQLColumnExpression[object]
) -> ColumnElement[float]:
    return func.ST_Distance(a, b, type_=Float)
