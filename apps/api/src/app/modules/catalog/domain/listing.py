"""A PG listing (ARCHITECTURE §6): who it is for, what it offers, how far it is verified, and
where it stands.

A property starts as a draft. Publishing needs something to sell: at least one active room
category with at least one active bed (step 2.5 adds the verification gate). A published property
can be paused and published again; any property can be delisted, and a delisted one goes back to
draft to be listed again.
"""

import itertools
import re
import unicodedata
from enum import StrEnum
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Collection

NAME_MAX_LENGTH: Final = 120
SLUG_MAX_LENGTH: Final = 80
# What slugify keeps, so that "-99999" still fits after it.
SLUG_BASE_MAX_LENGTH: Final = SLUG_MAX_LENGTH - 6
HOUSE_RULES_MAX: Final = 30
HOUSE_RULE_MAX_LENGTH: Final = 200


class GenderPolicy(StrEnum):
    BOYS = "boys"
    GIRLS = "girls"
    COED = "coed"


class Meals(StrEnum):
    NONE = "none"
    BREAKFAST = "breakfast"
    TWO = "two"
    THREE = "three"
    FOUR = "four"


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    SCHEDULED = "scheduled"
    VERIFIED = "verified"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class LicenceStatus(StrEnum):
    UNKNOWN = "unknown"
    APPLIED = "applied"
    LICENSED = "licensed"
    NOT_REQUIRED = "not_required"


class SocietyPermission(StrEnum):
    # Not in a housing society, so nobody's permission is needed.
    NOT_APPLICABLE = "n/a"
    ON_FILE = "on_file"
    MISSING = "missing"


class LocationPrecision(StrEnum):
    # The building's own pin, from a field agent's GPS or checked by ops.
    EXACT = "exact"
    # Close by, until someone checks it on the spot.
    APPROXIMATE = "approximate"


class PropertyStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    PAUSED = "paused"
    DELISTED = "delisted"


_NEXT: Final = {
    PropertyStatus.DRAFT: frozenset({PropertyStatus.PUBLISHED, PropertyStatus.DELISTED}),
    PropertyStatus.PUBLISHED: frozenset({PropertyStatus.PAUSED, PropertyStatus.DELISTED}),
    PropertyStatus.PAUSED: frozenset({PropertyStatus.PUBLISHED, PropertyStatus.DELISTED}),
    PropertyStatus.DELISTED: frozenset({PropertyStatus.DRAFT}),
}


def can_move(current: PropertyStatus, target: PropertyStatus) -> bool:
    return target in _NEXT[current]


def publishing_problems(*, sellable_categories: int) -> list[str]:
    """What stops a property going live; empty when it can."""
    if sellable_categories == 0:
        return ["needs at least one active room category with an active bed"]
    return []


def slugify(*parts: str) -> str:
    """A URL slug from a name and its locality: ``slugify("Asha's PG", "Kamla Nagar")`` is
    ``"ashas-pg-kamla-nagar"``. Accents are dropped; a name with no Latin letters or digits at
    all becomes ``"pg"``."""
    text = unicodedata.normalize("NFKD", " ".join(parts))
    ascii_text = text.encode("ascii", "ignore").decode().casefold().replace("'", "")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    return slug[:SLUG_BASE_MAX_LENGTH].rstrip("-") or "pg"


def numbered(slug: str, number: int) -> str:
    """The slug to try when ``slug`` is taken: ``numbered("x", 2) == "x-2"``."""
    suffix = f"-{number}"
    return slug[: SLUG_MAX_LENGTH - len(suffix)].rstrip("-") + suffix


def free_slug(base: str, taken: Collection[str]) -> str:
    """``base`` if it is free, else the first free numbered one: ``base-2``, ``base-3``, ...

    ``taken`` must hold ``base`` and every slug that starts with ``base-``. A base from
    ``slugify`` leaves room for any number up to 99999, so a numbered slug always starts with the
    whole base.
    """
    if base not in taken:
        return base
    return next(
        candidate for n in itertools.count(2) if (candidate := numbered(base, n)) not in taken
    )
