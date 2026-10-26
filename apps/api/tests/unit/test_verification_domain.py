"""Field verification's rules (step 2.5, ADR 0024), without a database."""

import dataclasses

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.catalog.domain.listing import SocietyPermission, VerificationStatus
from app.modules.catalog.domain.verification import (
    MAX_PHOTOS,
    NOTES_MAX_LENGTH,
    Checklist,
    Condition,
    Cracks,
    VisitResult,
    WomenSafety,
    can_schedule,
    can_suspend,
    checklist_problems,
    keeps_listing_live,
    report_problems,
    status_after,
)
from app.modules.catalog.repository import checklist_from_json, checklist_to_json

SAFE = Checklist(
    building_age_years=12,
    condition=Condition.GOOD,
    cracks=Cracks.NONE,
    exits=2,
    fire_extinguishers=True,
    cctv=True,
    warden=True,
    women_safety=frozenset({WomenSafety.SECURE_ENTRY}),
    licence_number=None,
    society_permission=SocietyPermission.NOT_APPLICABLE,
    authority_notice=False,
)

checklists = st.builds(
    Checklist,
    building_age_years=st.none() | st.integers(min_value=0, max_value=200),
    condition=st.sampled_from(Condition),
    cracks=st.sampled_from(Cracks),
    exits=st.integers(min_value=0, max_value=20),
    fire_extinguishers=st.booleans(),
    cctv=st.booleans(),
    warden=st.booleans(),
    women_safety=st.frozensets(st.sampled_from(WomenSafety)),
    licence_number=st.none() | st.text(min_size=1, max_size=20).filter(str.strip),
    society_permission=st.sampled_from(SocietyPermission),
    authority_notice=st.booleans(),
)


def test_a_safe_building_passes_with_a_photo() -> None:
    assert report_problems(SAFE, VisitResult.PASSED, notes="", photos=1) == []


def test_a_building_with_a_notice_from_the_authorities_cant_pass() -> None:
    flagged = dataclasses.replace(SAFE, authority_notice=True)

    assert report_problems(flagged, VisitResult.PASSED, notes="", photos=1) == [
        "a building with a notice from the authorities can't pass"
    ]
    assert report_problems(flagged, VisitResult.FAILED, notes="Sealed", photos=1) == []


def test_everything_else_is_the_agents_judgement() -> None:
    # Structural cracks, no extinguishers, one exit: evidence for the agent, not a rule.
    worn = dataclasses.replace(
        SAFE, condition=Condition.POOR, cracks=Cracks.STRUCTURAL, exits=1, fire_extinguishers=False
    )

    assert report_problems(worn, VisitResult.PASSED, notes="", photos=1) == []


def test_a_failed_visit_says_why() -> None:
    assert report_problems(SAFE, VisitResult.FAILED, notes="  ", photos=1) == [
        "a failed visit needs notes saying why"
    ]


@pytest.mark.parametrize("photos", [0, MAX_PHOTOS + 1])
def test_a_report_takes_one_to_twenty_photos(photos: int) -> None:
    assert report_problems(SAFE, VisitResult.PASSED, notes="", photos=photos)


def test_notes_have_a_limit() -> None:
    notes = "x" * (NOTES_MAX_LENGTH + 1)

    assert report_problems(SAFE, VisitResult.FAILED, notes=notes, photos=1)


@pytest.mark.parametrize(
    "answers",
    [
        {"building_age_years": -1},
        {"building_age_years": 201},
        {"exits": -1},
        {"exits": 21},
        {"licence_number": " "},
        {"licence_number": "x" * 101},
    ],
)
def test_answers_out_of_range_are_refused(answers: dict[str, object]) -> None:
    assert checklist_problems(dataclasses.replace(SAFE, **answers))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("status", "schedulable"),
    [
        (VerificationStatus.UNVERIFIED, True),
        (VerificationStatus.REJECTED, True),
        (VerificationStatus.SUSPENDED, True),
        # One visit at a time, and a verified property isn't verified again yet.
        (VerificationStatus.SCHEDULED, False),
        (VerificationStatus.VERIFIED, False),
    ],
)
def test_a_visit_is_booked_for_a_property_not_vouched_for(
    status: VerificationStatus, schedulable: bool
) -> None:
    assert can_schedule(status) is schedulable


def test_the_result_sets_the_status_and_only_a_verified_property_is_suspended() -> None:
    assert status_after(VisitResult.PASSED) is VerificationStatus.VERIFIED
    assert status_after(VisitResult.FAILED) is VerificationStatus.REJECTED
    assert [status for status in VerificationStatus if can_suspend(status)] == [
        VerificationStatus.VERIFIED
    ]


def test_a_failed_or_suspended_building_doesnt_stay_live() -> None:
    assert {status for status in VerificationStatus if not keeps_listing_live(status)} == {
        VerificationStatus.REJECTED,
        VerificationStatus.SUSPENDED,
    }


@given(checklists)
def test_a_checklist_is_stored_and_read_back_unchanged(checklist: Checklist) -> None:
    assert checklist_from_json(checklist_to_json(checklist)) == checklist
