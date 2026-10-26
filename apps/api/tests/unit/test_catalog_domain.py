"""The catalog's rules (step 2.2): the listing's life, slugs, rents, charges, beds per room and
display points."""

import random
import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.geometry import NCR_BOUNDS, Point, distance_m
from app.core.money import Paise, rupees
from app.modules.catalog.domain.charges import (
    MAX_CHARGES,
    ChargeKind,
    MeteredCharge,
    MonthlyCharge,
    OneTimeCharge,
    charge_problems,
    monthly_total,
    one_time_total,
)
from app.modules.catalog.domain.listing import (
    SLUG_MAX_LENGTH,
    PropertyStatus,
    VerificationStatus,
    can_move,
    free_slug,
    next_statuses,
    numbered,
    publishing_problems,
    slugify,
)
from app.modules.catalog.domain.location import (
    MAX_OFFSET_M,
    MIN_OFFSET_M,
    Offset,
    moved,
    random_offset,
)
from app.modules.catalog.domain.owners import normalize_gstin
from app.modules.catalog.domain.rooms import BEDS_PER_ROOM, Occupancy, rent_problems, room_has_space

ncr_points = st.builds(
    Point,
    lat=st.floats(min_value=NCR_BOUNDS.south, max_value=NCR_BOUNDS.north),
    lng=st.floats(min_value=NCR_BOUNDS.west, max_value=NCR_BOUNDS.east),
)


@pytest.mark.parametrize(
    ("current", "target", "allowed"),
    [
        (PropertyStatus.DRAFT, PropertyStatus.PUBLISHED, True),
        (PropertyStatus.DRAFT, PropertyStatus.DELISTED, True),
        (PropertyStatus.DRAFT, PropertyStatus.PAUSED, False),
        (PropertyStatus.PUBLISHED, PropertyStatus.PAUSED, True),
        (PropertyStatus.PUBLISHED, PropertyStatus.DELISTED, True),
        (PropertyStatus.PUBLISHED, PropertyStatus.DRAFT, False),
        (PropertyStatus.PAUSED, PropertyStatus.PUBLISHED, True),
        (PropertyStatus.PAUSED, PropertyStatus.DELISTED, True),
        (PropertyStatus.DELISTED, PropertyStatus.DRAFT, True),
        (PropertyStatus.DELISTED, PropertyStatus.PUBLISHED, False),
    ],
)
def test_a_listing_moves_only_as_the_state_machine_says(
    current: PropertyStatus, target: PropertyStatus, allowed: bool
) -> None:
    assert can_move(current, target) is allowed


def test_no_status_moves_to_itself() -> None:
    assert not any(can_move(status, status) for status in PropertyStatus)


@pytest.mark.parametrize("current", list(PropertyStatus))
def test_the_next_statuses_are_exactly_those_it_can_move_to(current: PropertyStatus) -> None:
    assert set(next_statuses(current)) == {
        target for target in PropertyStatus if can_move(current, target)
    }
    assert next_statuses(PropertyStatus.DRAFT) == [
        PropertyStatus.PUBLISHED,
        PropertyStatus.DELISTED,
    ]


def test_publishing_needs_something_to_sell() -> None:
    verified = VerificationStatus.VERIFIED

    assert publishing_problems(sellable_categories=0, verification=verified, verified_only=True)
    assert (
        publishing_problems(sellable_categories=1, verification=verified, verified_only=True) == []
    )


@pytest.mark.parametrize(
    ("verification", "verified_only", "publishable"),
    [
        (VerificationStatus.VERIFIED, True, True),
        (VerificationStatus.UNVERIFIED, True, False),
        (VerificationStatus.SCHEDULED, True, False),
        (VerificationStatus.UNVERIFIED, False, True),
        (VerificationStatus.SCHEDULED, False, True),
        # A building that failed its checks, or was suspended, never goes live.
        (VerificationStatus.REJECTED, False, False),
        (VerificationStatus.SUSPENDED, False, False),
    ],
)
def test_publishing_needs_a_passed_verification_while_the_flag_says_so(
    verification: VerificationStatus, verified_only: bool, publishable: bool
) -> None:
    problems = publishing_problems(
        sellable_categories=1, verification=verification, verified_only=verified_only
    )

    assert (problems == []) is publishable


@pytest.mark.parametrize(
    ("parts", "slug"),
    [
        (("Asha's PG", "Kamla Nagar"), "ashas-pg-kamla-nagar"),
        (("Café  Résidence", "Vijay Nagar"), "cafe-residence-vijay-nagar"),
        (("--PG--",), "pg"),
        (("आशा पीजी",), "pg"),
        (("Sunrise House No. 12",), "sunrise-house-no-12"),
    ],
)
def test_slugs_are_lowercase_words_joined_by_hyphens(parts: tuple[str, ...], slug: str) -> None:
    assert slugify(*parts) == slug


@given(st.text(max_size=300), st.integers(min_value=2, max_value=999))
def test_any_name_makes_a_valid_slug_numbered_ones_too(name: str, number: int) -> None:
    pattern = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
    slug = slugify(name)
    again = numbered(slug, number)

    assert pattern.fullmatch(slug)
    assert len(slug) <= SLUG_MAX_LENGTH
    assert pattern.fullmatch(again)
    assert len(again) <= SLUG_MAX_LENGTH
    assert again.endswith(f"-{number}")


@pytest.mark.parametrize(
    ("base", "low", "high", "deposit", "problems"),
    [
        (rupees(9_000), None, None, rupees(9_000), 0),
        (rupees(9_000), rupees(8_000), rupees(12_000), Paise(0), 0),
        (rupees(9_000), rupees(9_000), rupees(9_000), Paise(0), 0),
        (Paise(0), None, None, Paise(0), 1),
        (rupees(9_000), rupees(9_500), None, Paise(0), 1),
        (rupees(9_000), None, rupees(8_500), Paise(0), 1),
        (rupees(9_000), Paise(0), None, Paise(0), 1),
        (rupees(9_000), None, None, Paise(-1), 1),
    ],
)
def test_the_base_rent_is_positive_and_inside_the_owners_range(
    base: Paise, low: Paise | None, high: Paise | None, deposit: Paise, problems: int
) -> None:
    found = rent_problems(base_rent=base, owner_min=low, owner_max=high, deposit=deposit)

    assert len(found) == problems


@pytest.mark.parametrize("occupancy", list(Occupancy))
def test_a_room_holds_as_many_beds_as_its_occupancy(occupancy: Occupancy) -> None:
    beds = BEDS_PER_ROOM[occupancy]

    assert room_has_space(occupancy, beds - 1)
    assert not room_has_space(occupancy, beds)


def test_charges_add_up_monthly_with_estimates_and_once_at_move_in() -> None:
    charges = (
        MonthlyCharge(ChargeKind.MAINTENANCE, "Maintenance", rupees(500)),
        MeteredCharge(
            ChargeKind.ELECTRICITY,
            "Electricity",
            rate=rupees(9),
            unit="kWh",
            monthly_estimate=rupees(800),
        ),
        OneTimeCharge(ChargeKind.REGISTRATION, "Registration", rupees(1_000)),
    )

    assert charge_problems(charges) == []
    assert monthly_total(charges) == rupees(1_300)
    assert one_time_total(charges) == rupees(1_000)


@pytest.mark.parametrize(
    "charges",
    [
        (MonthlyCharge(ChargeKind.INTERNET, "Wi-Fi", Paise(0)),),
        (MonthlyCharge(ChargeKind.INTERNET, " ", rupees(300)),),
        (
            MeteredCharge(
                ChargeKind.ELECTRICITY,
                "Electricity",
                rate=rupees(9),
                unit="",
                monthly_estimate=rupees(1),
            ),
        ),
        (
            MeteredCharge(
                ChargeKind.ELECTRICITY,
                "Electricity",
                rate=rupees(9),
                unit="kWh",
                monthly_estimate=Paise(0),
            ),
        ),
        (
            MonthlyCharge(ChargeKind.LAUNDRY, "Laundry", rupees(300)),
            MonthlyCharge(ChargeKind.LAUNDRY, "laundry", rupees(200)),
        ),
        tuple(
            MonthlyCharge(ChargeKind.OTHER, f"Charge {n}", rupees(1))
            for n in range(MAX_CHARGES + 1)
        ),
    ],
)
def test_charges_that_cant_be_shown_honestly_are_refused(
    charges: tuple[MonthlyCharge | MeteredCharge, ...],
) -> None:
    assert charge_problems(charges)


@given(ncr_points, st.randoms(use_true_random=False))
def test_a_display_point_is_80_to_150_m_from_the_exact_one(
    exact: Point, rng: random.Random
) -> None:
    offset = random_offset(rng)
    display = moved(exact, offset)

    assert MIN_OFFSET_M <= offset.distance_m <= MAX_OFFSET_M
    # Seven decimals of rounding move a point by at most about 1.5 cm.
    assert distance_m(exact, display) == pytest.approx(offset.distance_m, abs=0.05)


def test_moving_north_raises_only_the_latitude() -> None:
    exact = Point(lat=28.6, lng=77.2)

    north = moved(exact, Offset(bearing_deg=0.0, distance_m=100.0))

    assert north.lng == exact.lng
    assert north.lat > exact.lat


@pytest.mark.parametrize(
    ("raw", "stored"),
    [
        ("07aaacb1234f1z5", "07AAACB1234F1Z5"),
        ("07 AAACB 1234F 1Z5", "07AAACB1234F1Z5"),
        ("07AAACB1234F1Y5", None),
        ("AAACB1234F", None),
    ],
)
def test_a_gstin_is_stored_in_capitals_or_refused(raw: str, stored: str | None) -> None:
    # Made-up numbers in the GSTIN's shape: the check digit comes in step 2.6.
    assert normalize_gstin(raw) == stored


def test_a_taken_slug_gets_the_first_free_number_however_many_are_taken() -> None:
    base = slugify("Fictional Residency", "Kamla Nagar")
    taken = {base, *(numbered(base, n) for n in range(2, 500))}

    assert free_slug("free-slug", taken) == "free-slug"
    assert free_slug(base, {base}) == f"{base}-2"
    assert free_slug(base, taken) == f"{base}-500"


@given(st.text(min_size=1, max_size=300))
def test_a_numbered_slug_keeps_the_whole_base(name: str) -> None:
    base = slugify(name)

    assert numbered(base, 99_999).startswith(f"{base}-")
