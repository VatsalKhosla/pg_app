"""Owners and their PGs from a spreadsheet (ADR 0072): the file ops fill in from an owner's answers,
read and checked before anything is made. Pure.

One row per room type. Rows with the same owner phone and PG name are one PG, whose details come
from its first row. Rent and deposit are whole rupees, as people write them ("6,000" works); the
rest are the words the ops console uses. A PG without both latitude and longitude is still read:
its owner can be added, and the PG waits for ops to drop its pin.
"""

import csv
import io
from dataclasses import dataclass, field
from typing import Final

from app.modules.catalog.domain.listing import GenderPolicy, Meals
from app.modules.catalog.domain.rooms import Occupancy
from app.modules.identity.domain.emails import normalize_email
from app.modules.identity.domain.phones import normalize_indian_mobile

# The most a file may hold: a day's onboarding, not a migration.
MAX_ROWS: Final = 200
MAX_TEXT: Final = 200_000
PAISE_PER_RUPEE: Final = 100
# Lists inside a cell are separated by semicolons.
SEPARATOR: Final = ";"

REQUIRED: Final = (
    "owner_name",
    "owner_phone",
    "pg_name",
    "locality",
    "address",
    "gender",
    "room_type",
    "rent",
    "deposit",
)
OPTIONAL: Final = (
    "owner_email",
    "business_name",
    "legal_name",
    "latitude",
    "longitude",
    "meals",
    "house_rules",
    "amenities",
    "description",
    "room_label",
    "ac",
    "attached_bath",
    "balcony",
)
COLUMNS: Final = REQUIRED + OPTIONAL

# What a room type is called when the row doesn't say.
LABELS: Final = {
    Occupancy.SINGLE: "Single",
    Occupancy.DOUBLE: "Twin sharing",
    Occupancy.TRIPLE: "Triple sharing",
    Occupancy.QUAD: "Four sharing",
}
_YES: Final = frozenset({"yes", "y", "true", "1"})
_NO: Final = frozenset({"", "no", "n", "false", "0"})


@dataclass(frozen=True, slots=True)
class ImportedRoomType:
    occupancy: Occupancy
    label: str
    rent_paise: int
    deposit_paise: int
    ac: bool
    attached_bath: bool
    balcony: bool


@dataclass(frozen=True, slots=True)
class ImportedPg:
    """One PG and its owner, as the file describes them."""

    # The file's first row for this PG (1 is the first after the header).
    row: int
    owner_name: str
    owner_phone: str
    owner_email: str | None
    business_name: str
    legal_name: str
    name: str
    locality: str
    address: str
    # (latitude, longitude), or None until ops drop the pin.
    location: tuple[float, float] | None
    gender_policy: GenderPolicy
    meals: Meals
    house_rules: tuple[str, ...]
    amenities: tuple[str, ...]
    description: str
    room_types: tuple[ImportedRoomType, ...]


@dataclass(frozen=True, slots=True)
class ParsedImport:
    pgs: tuple[ImportedPg, ...]
    # "Row 4: ..." for every row that can't be read; those rows are left out.
    problems: tuple[str, ...]


@dataclass
class _Draft:
    first: dict[str, str]
    row: int
    room_types: list[ImportedRoomType] = field(default_factory=list)


def _rupees(value: str, what: str) -> int:
    text = value.replace(",", "").replace("₹", "").strip()
    if not text.isdigit():
        msg = f"{what} must be whole rupees, like 6000"
        raise ValueError(msg)
    return int(text) * PAISE_PER_RUPEE


def _yes(value: str, what: str) -> bool:
    text = value.strip().lower()
    if text in _YES:
        return True
    if text in _NO:
        return False
    msg = f"{what} must be yes or no"
    raise ValueError(msg)


def _choice[E: (GenderPolicy, Meals, Occupancy)](kind: type[E], value: str, what: str) -> E:
    text = value.strip().lower()
    for option in kind:
        if option.value == text:
            return option
    msg = f"{what} must be one of {', '.join(option.value for option in kind)}"
    raise ValueError(msg)


def _list(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(SEPARATOR) if item.strip())


def _location(row: dict[str, str]) -> tuple[float, float] | None:
    latitude, longitude = row.get("latitude", "").strip(), row.get("longitude", "").strip()
    if not latitude and not longitude:
        return None
    try:
        return float(latitude), float(longitude)
    except ValueError:
        msg = "latitude and longitude must both be numbers, or both empty"
        raise ValueError(msg) from None


def _room_type(row: dict[str, str]) -> ImportedRoomType:
    occupancy = _choice(Occupancy, row["room_type"], "room_type")
    return ImportedRoomType(
        occupancy=occupancy,
        label=row.get("room_label", "").strip() or LABELS[occupancy],
        rent_paise=_rupees(row["rent"], "rent"),
        deposit_paise=_rupees(row["deposit"], "deposit"),
        ac=_yes(row.get("ac", ""), "ac"),
        attached_bath=_yes(row.get("attached_bath", ""), "attached_bath"),
        balcony=_yes(row.get("balcony", ""), "balcony"),
    )


def _pg(draft: _Draft) -> ImportedPg:
    first = draft.first
    phone = normalize_indian_mobile(first["owner_phone"])
    if phone is None:
        msg = "owner_phone isn't a 10-digit Indian mobile number"
        raise ValueError(msg)
    raw_email = first.get("owner_email", "").strip()
    email = normalize_email(raw_email) if raw_email else None
    if raw_email and email is None:
        msg = "owner_email isn't an email address"
        raise ValueError(msg)
    owner_name = first["owner_name"].strip()
    name = first["pg_name"].strip()
    return ImportedPg(
        row=draft.row,
        owner_name=owner_name,
        owner_phone=phone,
        owner_email=email,
        business_name=first.get("business_name", "").strip() or name,
        legal_name=first.get("legal_name", "").strip() or owner_name,
        name=name,
        locality=first["locality"].strip().lower(),
        address=first["address"].strip(),
        location=_location(first),
        gender_policy=_choice(GenderPolicy, first["gender"], "gender"),
        meals=_choice(Meals, first.get("meals", "") or "none", "meals"),
        house_rules=_list(first.get("house_rules", "")),
        amenities=tuple(slug.lower() for slug in _list(first.get("amenities", ""))),
        description=first.get("description", "").strip(),
        room_types=tuple(draft.room_types),
    )


def parse_listing_import(text: str) -> ParsedImport:
    """The PGs a filled-in template describes, and every problem with its rows."""
    if len(text) > MAX_TEXT:
        return ParsedImport((), (f"The file is over {MAX_TEXT:,} characters: split it.",))
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    headers = {name.strip().lower() for name in reader.fieldnames or ()}
    if missing := [name for name in REQUIRED if name not in headers]:
        return ParsedImport((), (f"Columns missing: {', '.join(missing)}.",))
    problems: list[str] = []
    drafts: dict[tuple[str, str], _Draft] = {}
    for number, raw in enumerate(reader, start=1):
        if number > MAX_ROWS:
            problems.append(f"Only the first {MAX_ROWS} rows are read: split the file.")
            break
        row = {key.strip().lower(): (value or "") for key, value in raw.items() if key}
        if not any(value.strip() for value in row.values()):
            continue
        empty = [name for name in REQUIRED if not row.get(name, "").strip()]
        if empty:
            problems.append(f"Row {number}: {', '.join(empty)} empty.")
            continue
        phone = normalize_indian_mobile(row["owner_phone"]) or row["owner_phone"].strip()
        key = (phone, row["pg_name"].strip().casefold())
        draft = drafts.setdefault(key, _Draft(first=row, row=number))
        try:
            draft.room_types.append(_room_type(row))
        except ValueError as error:
            problems.append(f"Row {number}: {error}.")
    pgs: list[ImportedPg] = []
    for draft in drafts.values():
        if not draft.room_types:
            continue
        try:
            pgs.append(_pg(draft))
        except ValueError as error:
            problems.append(f"Row {draft.row}: {error}.")
    return ParsedImport(tuple(pgs), tuple(problems))
