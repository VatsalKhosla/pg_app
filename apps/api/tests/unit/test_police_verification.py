"""Police verification without a database (ADR 0070): its states, the details' rules, and above all
that no Aadhaar number gets in, whichever field it's typed into."""

from dataclasses import replace
from datetime import date
from itertools import product
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from app.modules.agreements.domain.verification import (
    Address,
    IdType,
    Occupation,
    PoliceVerificationStatus,
    Reference,
    TenantDetails,
    VerificationEvent,
    VerificationRefusedError,
    advance,
    allowed,
    from_json,
    holds_aadhaar_like_number,
    problems,
    to_json,
)
from app.modules.agreements.schemas import TenantDetailsInput
from app.modules.identity.domain.profile import Gender

V = PoliceVerificationStatus
VE = VerificationEvent
ALLOWED = {
    (V.NOT_STARTED, VE.GIVE_DETAILS): V.DETAILS_SUBMITTED,
    (V.DETAILS_SUBMITTED, VE.GIVE_DETAILS): V.DETAILS_SUBMITTED,
    (V.DETAILS_SUBMITTED, VE.SUBMIT_TO_POLICE): V.SUBMITTED_TO_POLICE,
    (V.SUBMITTED_TO_POLICE, VE.MARK_VERIFIED): V.VERIFIED,
}
TODAY = date(2027, 8, 1)
DETAILS = TenantDetails(
    full_name="Asha Verma",
    parent_name="Ravi Verma",
    date_of_birth=date(2007, 3, 9),
    gender=Gender.FEMALE,
    phone_e164="+919876500001",
    permanent_address=Address(
        line="House 1, a fictional lane",
        city="Fictional Town",
        district="Fictional District",
        state="Fictional State",
        pin_code="123456",
        police_station=None,
    ),
    occupation=Occupation.STUDENT,
    institution="A fictional college, Delhi",
    id_type=IdType.PASSPORT,
    id_last4="567K",
    references=(Reference("Meera Rao", "+919876500002", "Aunt"),),
)


@pytest.mark.parametrize(("status", "event"), list(product(V, VE)))
def test_a_verification_moves_only_along_its_table(status: V, event: VE) -> None:
    if (status, event) in ALLOWED:
        assert advance(status, event, booking_ended=False) is ALLOWED[status, event]
        assert allowed(status, event, booking_ended=False)
    else:
        with pytest.raises(VerificationRefusedError):
            advance(status, event, booking_ended=False)
        assert not allowed(status, event, booking_ended=False)


@pytest.mark.parametrize(("status", "event"), list(ALLOWED))
def test_nothing_moves_once_the_booking_has_ended(status: V, event: VE) -> None:
    with pytest.raises(VerificationRefusedError, match="booking has ended"):
        advance(status, event, booking_ended=True)


@given(st.lists(st.sampled_from(list(VE)), max_size=10))
def test_a_verification_only_ever_goes_forward(events: list[VE]) -> None:
    order = list(V)
    status = V.NOT_STARTED
    for event in events:
        try:
            after = advance(status, event, booking_ended=False)
        except VerificationRefusedError:
            continue
        assert order.index(after) >= order.index(status)
        status = after


@pytest.mark.parametrize(
    "text",
    [
        "123412341234",
        "1234 1234 1234",
        "1234-1234-1234",
        "1234.1234.1234",
        "my aadhaar is 2345 6789 0123, thanks",
        "१२३४ ५६७८ ९०१२",
        "VID 9123 4567 8901 2345",
    ],
)
def test_anything_shaped_like_an_aadhaar_number_is_caught(text: str) -> None:
    assert holds_aadhaar_like_number(text)


@pytest.mark.parametrize(
    "text",
    ["9876543210", "House 12, Block 34, Sector 56", "110001", "1234 5678", "ABCD1234EFGH"],
)
def test_ordinary_text_is_left_alone(text: str) -> None:
    assert not holds_aadhaar_like_number(text)


@given(
    number=st.from_regex(r"[0-9]{12}", fullmatch=True),
    separator=st.sampled_from(["", " ", "-", "."]),
    before=st.text(alphabet="abc ,", max_size=8),
    after=st.text(alphabet="abc ,", max_size=8),
)
def test_no_twelve_digit_number_slips_through(
    number: str, separator: str, before: str, after: str
) -> None:
    grouped = separator.join((number[:4], number[4:8], number[8:]))
    assert holds_aadhaar_like_number(f"{before}{grouped}{after}")


def test_good_details_have_no_problems() -> None:
    assert problems(DETAILS, today=TODAY) == []


@pytest.mark.parametrize(
    ("changes", "problem"),
    [
        ({"institution": "College, roll 1234 5678 9012"}, "Aadhaar"),
        ({"id_type": IdType.AADHAAR, "id_last4": "12AB"}, "digits"),
        ({"id_last4": "12-4"}, "last four"),
        ({"date_of_birth": date(2020, 1, 1)}, "years old"),
        ({"date_of_birth": date(2028, 1, 1)}, "years old"),
        ({"date_of_birth": date(1920, 1, 1)}, "years old"),
        ({"references": (Reference("Ravi", "+919876500001", "Father"),)}, "other than yours"),
        (
            {
                "references": tuple(
                    Reference(f"R{n}", f"+9198765000{n}9", "Friend") for n in range(3)
                )
            },
            "at most 2",
        ),
    ],
)
def test_details_the_police_form_cant_take_are_refused(
    changes: dict[str, Any], problem: str
) -> None:
    found = problems(replace(DETAILS, **changes), today=TODAY)

    assert any(problem in item for item in found), found


def test_an_aadhaar_number_in_the_address_is_refused() -> None:
    address = replace(DETAILS.permanent_address, line="Flat 2, 2345 6789 0123")

    assert problems(replace(DETAILS, permanent_address=address), today=TODAY) == [
        "Leave out Aadhaar numbers: we never keep one."
    ]


def test_details_survive_sealing_as_json_unchanged() -> None:
    assert from_json(to_json(DETAILS)) == DETAILS
    assert from_json(to_json(replace(DETAILS, references=()))) == replace(DETAILS, references=())


def _body(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "fullName": "Asha Verma",
        "parentName": "Ravi Verma",
        "dateOfBirth": "2007-03-09",
        "gender": "female",
        "phone": "98765 00001",
        "permanentAddress": {
            "line": "House 1, a fictional lane",
            "city": "Fictional Town",
            "district": "Fictional District",
            "state": "Fictional State",
            "pinCode": "123456",
        },
        "occupation": "student",
        "institution": "A fictional college, Delhi",
        "idType": "passport",
        "idLast4": "567k",
        "references": [],
        "consent": True,
    }
    return body | changes


def test_the_form_takes_the_last_four_characters_only_and_tidies_them() -> None:
    parsed = TenantDetailsInput.model_validate(_body())

    assert parsed.id_last4 == "567K"
    assert parsed.phone == "+919876500001"
    with pytest.raises(ValidationError):
        TenantDetailsInput.model_validate(_body(idLast4="2345 6789 0123"))
    with pytest.raises(ValidationError):
        TenantDetailsInput.model_validate(_body(idLast4="12345"))


@pytest.mark.parametrize(
    "changes",
    [
        {"fullName": "Asha 234567890123"},
        {"institution": "Roll no. 2345-6789-0123"},
        {"permanentAddress": {**_body()["permanentAddress"], "line": "2345 6789 0123, Delhi"}},
        {"references": [{"name": "Meera 234567890123", "phone": "9876500002", "relation": "Aunt"}]},
    ],
)
def test_the_form_refuses_an_aadhaar_number_in_any_field(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="Aadhaar"):
        TenantDetailsInput.model_validate(_body(**changes))


@pytest.mark.parametrize("consent", [False, None, "yes"])
def test_nothing_is_shared_without_a_ticked_consent(consent: object) -> None:
    with pytest.raises(ValidationError):
        TenantDetailsInput.model_validate(_body(consent=consent))
