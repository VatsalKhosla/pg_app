"""Field verification (step 2.5, ADR 0024): a field agent visits a PG, goes through the safety
checklist on their phone, and the result sets the property's verification status.

A visit is scheduled by ops for one agent, then submitted by that agent (or cancelled by ops). The
agent's position and the time are recorded with the report, and so is how far the agent stood
from the building's pin. Only what the founders' rules say is decided here: a building with a
notice from the authorities can't pass ("never list a flagged building", PRODUCT_CONTEXT §7), and
a failed visit says why. Every other answer is evidence for the agent's own judgement.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from app.modules.catalog.domain.listing import SocietyPermission, VerificationStatus


class VisitStatus(StrEnum):
    SCHEDULED = "scheduled"
    SUBMITTED = "submitted"
    CANCELLED = "cancelled"


class VisitResult(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


class Condition(StrEnum):
    """The building as a whole, as the agent sees it."""

    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"


class Cracks(StrEnum):
    NONE = "none"
    # Hairline cracks in plaster.
    MINOR = "minor"
    # Cracks through walls, beams or columns.
    STRUCTURAL = "structural"


class WomenSafety(StrEnum):
    """Features that make a PG safer for women, ticked where the agent saw them."""

    # A woman warden or caretaker on site.
    WOMAN_STAFF = "woman_staff"
    # Entry by key card, biometrics or a guard.
    SECURE_ENTRY = "secure_entry"
    # A well-lit street and entrance at night.
    LIT_APPROACH = "lit_approach"
    # Visitors signed in and out.
    VISITOR_LOG = "visitor_log"
    # In co-living, women's rooms on floors of their own.
    SEPARATE_FLOORS = "separate_floors"


# The statuses a visit can be scheduled from: never verified, failed, or suspended. A verified
# property is verified again once re-verification exists (Phase 3).
SCHEDULABLE: Final = frozenset(
    {VerificationStatus.UNVERIFIED, VerificationStatus.REJECTED, VerificationStatus.SUSPENDED}
)

OLDEST_BUILDING_YEARS: Final = 200
MOST_EXITS: Final = 20
NOTES_MAX_LENGTH: Final = 2_000
LICENCE_NUMBER_MAX_LENGTH: Final = 100
REASON_MAX_LENGTH: Final = 500
# Photos a report takes: at least one, as evidence of the visit.
MIN_PHOTOS: Final = 1
MAX_PHOTOS: Final = 20
# How far ahead a visit may be booked.
MAX_DAYS_AHEAD: Final = 60


@dataclass(frozen=True, slots=True)
class Checklist:
    """The agent's answers, on site."""

    # As the owner or a document says; None if nobody knows.
    building_age_years: int | None
    condition: Condition
    cracks: Cracks
    # Separate ways out of the building.
    exits: int
    # Present, charged and in date.
    fire_extinguishers: bool
    # Covering the entrance and the common areas.
    cctv: bool
    # Someone in charge on site at night.
    warden: bool
    women_safety: frozenset[WomenSafety]
    # As shown on the licence on site; None if there is none to see.
    licence_number: str | None
    society_permission: SocietyPermission
    # A sealing, demolition or unsafe-building notice from the authorities.
    authority_notice: bool


def checklist_problems(checklist: Checklist) -> list[str]:
    problems = []
    age = checklist.building_age_years
    if age is not None and not 0 <= age <= OLDEST_BUILDING_YEARS:
        problems.append(f"the building's age must be from 0 to {OLDEST_BUILDING_YEARS} years")
    if not 0 <= checklist.exits <= MOST_EXITS:
        problems.append(f"the exits must be from 0 to {MOST_EXITS}")
    number = checklist.licence_number
    if number is not None and not 0 < len(number.strip()) <= LICENCE_NUMBER_MAX_LENGTH:
        problems.append(f"the licence number needs 1 to {LICENCE_NUMBER_MAX_LENGTH} characters")
    return problems


def report_problems(
    checklist: Checklist, result: VisitResult, *, notes: str, photos: int
) -> list[str]:
    """What stops a report being submitted; empty when nothing does."""
    problems = checklist_problems(checklist)
    if result is VisitResult.PASSED and checklist.authority_notice:
        problems.append("a building with a notice from the authorities can't pass")
    if result is VisitResult.FAILED and not notes.strip():
        problems.append("a failed visit needs notes saying why")
    if len(notes) > NOTES_MAX_LENGTH:
        problems.append(f"the notes can have at most {NOTES_MAX_LENGTH} characters")
    if not MIN_PHOTOS <= photos <= MAX_PHOTOS:
        problems.append(f"a report needs {MIN_PHOTOS} to {MAX_PHOTOS} photos")
    return problems


def can_schedule(status: VerificationStatus) -> bool:
    return status in SCHEDULABLE


def status_after(result: VisitResult) -> VerificationStatus:
    """The property's verification status once a report with ``result`` is in."""
    return (
        VerificationStatus.VERIFIED if result is VisitResult.PASSED else VerificationStatus.REJECTED
    )


def can_suspend(status: VerificationStatus) -> bool:
    """Only a verified property can be suspended: anything else isn't vouched for anyway."""
    return status is VerificationStatus.VERIFIED


def keeps_listing_live(status: VerificationStatus) -> bool:
    """Whether a published listing may stay published with this verification status. A failed or
    suspended one comes down at once: a building that failed its checks isn't shown."""
    return status not in {VerificationStatus.REJECTED, VerificationStatus.SUSPENDED}
