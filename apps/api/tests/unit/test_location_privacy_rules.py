"""What the public may see of a PG (step 2.7, ADR 0026), without a database."""

import pytest

from app.core.money import Paise
from app.core.pii import contains_phone
from app.modules.catalog.domain.charges import ChargeKind, MonthlyCharge, charge_problems
from app.modules.catalog.domain.listing import PropertyStatus, VerificationStatus, is_public
from app.modules.catalog.domain.privacy import contact_shown, phone_problems
from app.modules.catalog.service.checks import house_rule_problems, text_problems

PUBLISHED = PropertyStatus.PUBLISHED


@pytest.mark.parametrize("status", [status for status in PropertyStatus if status is not PUBLISHED])
def test_only_a_published_listing_is_public(status: PropertyStatus) -> None:
    assert not is_public(status, VerificationStatus.VERIFIED, verified_only=False)


@pytest.mark.parametrize(
    ("verification", "verified_only", "public"),
    [
        (VerificationStatus.VERIFIED, True, True),
        (VerificationStatus.UNVERIFIED, True, False),
        (VerificationStatus.SCHEDULED, True, False),
        (VerificationStatus.UNVERIFIED, False, True),
        # A failed or suspended verification hides a listing whatever the flag says.
        (VerificationStatus.REJECTED, False, False),
        (VerificationStatus.SUSPENDED, False, False),
    ],
)
def test_a_published_listing_is_public_once_verified_as_publishing_needs(
    verification: VerificationStatus, verified_only: bool, public: bool
) -> None:
    assert is_public(PUBLISHED, verification, verified_only=verified_only) is public


@pytest.mark.parametrize(
    ("hidden", "entitled", "shown"),
    [(True, False, False), (True, True, True), (False, False, True), (False, True, True)],
)
def test_contact_details_show_when_not_hidden_or_once_entitled(
    hidden: bool, entitled: bool, shown: bool
) -> None:
    assert contact_shown(hide_owner_contact=hidden, entitled=entitled) is shown


@pytest.mark.parametrize(
    "text",
    [
        "Call 98765 43210",
        "WhatsApp 9876543210 for a discount",
        "+91 98765 43210",
        "+919876543210",
        "098765 43210",
        "91-98765-43210",
    ],
)
def test_a_phone_number_is_found_in_any_usual_form(text: str) -> None:
    assert contains_phone(text)
    assert phone_problems("the description", text) == [
        "the description can't include a phone number: owners' numbers show only after a visit"
    ]


@pytest.mark.parametrize(
    "text",
    [
        "Rent ₹12,000 a month, deposit ₹24,000",
        "Room 101, second floor, PIN 110007",
        "Open since 2015; gate closes at 22:30",
        "Five minutes from Vishwavidyalaya metro",
    ],
)
def test_ordinary_listing_text_is_left_alone(text: str) -> None:
    assert not contains_phone(text)
    assert phone_problems("the description", text) == []


def test_only_public_text_is_checked_for_a_phone_number() -> None:
    # Staff-only text, such as the address line, may hold any number.
    assert text_problems("the address", "House 9876543210", required=True, max_length=300) == []
    assert text_problems(
        "the name", "PG 9876543210", required=True, max_length=120, public=True
    ) == ["the name can't include a phone number: owners' numbers show only after a visit"]


def test_house_rules_and_charge_labels_can_carry_no_phone_number() -> None:
    assert house_rule_problems(["No smoking", "Warden: 98765 43210"]) == [
        "a house rule can't include a phone number: owners' numbers show only after a visit"
    ]
    charge = MonthlyCharge(
        kind=ChargeKind.MAINTENANCE, label="Pay 9876543210 for upkeep", amount=Paise(50_000)
    )
    assert charge_problems([charge]) == [
        "a charge's label can't include a phone number: owners' numbers show only after a visit"
    ]
