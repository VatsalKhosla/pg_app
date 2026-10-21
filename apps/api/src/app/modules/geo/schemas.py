"""Geo responses (ARCHITECTURE §15): public reference data. Distances are whole metres."""

from app.core.schemas import ApiModel


class Location(ApiModel):
    lat: float
    lng: float


class CityInfo(ApiModel):
    slug: str
    name: str
    center: Location


class CityList(ApiModel):
    items: list[CityInfo]


class LocalityInfo(ApiModel):
    slug: str
    city: str
    name: str
    center: Location


class LocalityList(ApiModel):
    items: list[LocalityInfo]


class MetroLineInfo(ApiModel):
    slug: str
    name: str
    # The line's colour, as #RRGGBB.
    colour: str


class MetroStationInfo(ApiModel):
    slug: str
    name: str
    location: Location
    lines: list[MetroLineInfo]


class MetroStationList(ApiModel):
    items: list[MetroStationInfo]


class StationDistance(ApiModel):
    station: MetroStationInfo
    distance_m: int


class LocalityDistance(ApiModel):
    locality: LocalityInfo
    # To the locality's boundary (0 inside it), or to its centre when it has no boundary.
    distance_m: int


class CampusInfo(ApiModel):
    slug: str
    city: str
    name: str
    location: Location
    nearest_station: StationDistance | None


class CampusList(ApiModel):
    items: list[CampusInfo]


class CampusDetail(CampusInfo):
    # The closest metro stations, nearest first.
    stations: list[StationDistance]
    # Localities within 2 km, nearest first.
    localities: list[LocalityDistance]
