"""Police verification in the API and the database (ADR 0070): the student gives the details, which
are kept sealed and never hold an Aadhaar number; the owner prints them, submits them with the
acknowledgement and marks them verified; ops read it all; every look at the details is audited;
the details are in the student's data export and erased 30 days after verification."""

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.config import Settings
from app.core.audit import AuditLog
from app.modules.agreements.models import TenantVerification
from app.modules.agreements.service import agreements_part, erase_police_details
from app.modules.media.domain.assets import Purpose
from tests.flags import FixedFlags
from tests.integration.test_booking_student import _again
from tests.integration.test_rent_agreements import RecordedCodes, _confirmed, _row
from tests.staff_api import Staff, run_as_staff

pytestmark = pytest.mark.integration


@pytest.fixture
def run(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Staff], Awaitable[Any]]) -> Any:
        settings = make_settings(database_url=database_url, redis_url=valkey_url)

        async def prepared(ops: Staff) -> Any:
            ops.app.state.flags = FixedFlags(remote_booking_enabled=True)
            ops.app.state.signing_code_sender = RecordedCodes()
            return await scenario(ops)

        return run_as_staff(settings, prepared)

    return run_scenario


def _details(**changes: Any) -> dict[str, Any]:
    details: dict[str, Any] = {
        "fullName": "Asha Verma",
        "parentName": "Ravi Verma",
        "dateOfBirth": "2007-03-09",
        "gender": "female",
        "phone": "98765 00001",
        "permanentAddress": {
            "line": "House 9, a fictional lane",
            "city": "Fictional Town",
            "district": "Fictional District",
            "state": "Fictional State",
            "pinCode": "123456",
            "policeStation": "Fictional Police Station",
        },
        "occupation": "student",
        "institution": "A fictional college, Delhi",
        "idType": "aadhaar",
        "idLast4": "4321",
        "references": [{"name": "Meera Rao", "phone": "9876500002", "relation": "Aunt"}],
        "consent": True,
    }
    return details | changes


def _paths(code: str) -> dict[str, str]:
    return {
        "student": f"/v1/bookings/{code}/police-verification",
        "owner": f"/v1/owner/bookings/{code}/police-verification",
        "ops": f"/v1/ops/bookings/{code}/police-verification",
    }


def test_a_student_gives_details_kept_sealed_and_never_an_aadhaar_number(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, owner, code = await _confirmed(ops)
        paths = _paths(code)
        seen: dict[str, Any] = {"before": await student.ok("GET", paths["student"])}
        seen["owner before"] = (await owner.call("POST", f"{paths['owner']}/mark-verified")).json()
        aadhaar = await student.call(
            "PUT", paths["student"], json=_details(institution="Roll 2345 6789 0123")
        )
        seen["aadhaar"] = (aadhaar.status_code, aadhaar.json()["code"], aadhaar.json()["errors"])
        too_young = await student.call(
            "PUT", paths["student"], json=_details(dateOfBirth="2020-01-01")
        )
        seen["too young"] = too_young.json()["code"]
        seen["given"] = await student.ok("PUT", paths["student"], json=_details())
        seen["corrected"] = await student.ok(
            "PUT", paths["student"], json=_details(institution="Another fictional college")
        )
        row = await _row(ops, code)
        async with ops.app.state.sessionmaker() as db:
            stored = await db.scalar(
                select(TenantVerification).where(TenantVerification.agreement_id == row.id)
            )
        assert stored is not None
        seen["stored"] = stored.details_sealed
        return seen

    seen = run(scenario)

    before = seen["before"]
    assert (before["status"], before["details"], before["canEdit"]) == ("not_started", None, True)
    assert seen["owner before"]["code"] == "INVALID_TRANSITION"
    status, code, errors = seen["aadhaar"]
    assert (status, code) == (422, "VALIDATION_ERROR")
    assert [error["pointer"] for error in errors] == ["/institution"]
    assert "2345" not in str(errors)
    assert seen["too young"] == "POLICE_DETAILS_INVALID"
    assert seen["given"]["status"] == "details_submitted"
    assert seen["given"]["details"]["idLast4"] == "4321"
    assert seen["corrected"]["details"]["institution"] == "Another fictional college"
    # Sealed: nothing personal is readable in the database.
    stored = seen["stored"]
    assert stored.startswith("v1.")
    assert "Asha" not in stored
    assert "Ravi" not in stored


def test_the_owner_prints_submits_and_marks_verified_and_ops_read_it(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, owner, code = await _confirmed(ops)
        paths = _paths(code)
        await student.ok("PUT", paths["student"], json=_details())
        seen: dict[str, Any] = {"owner reads": await owner.ok("GET", paths["owner"])}
        someone_elses = await ops.media(purpose=Purpose.DOCUMENT)
        photo = await owner.media(purpose=Purpose.LISTING_PHOTO)
        seen["refused"] = [
            (
                await owner.call(
                    "POST", f"{paths['owner']}/mark-submitted", json={"acknowledgement": media}
                )
            ).json()["code"]
            for media in (someone_elses, photo)
        ]
        receipt = await owner.media(purpose=Purpose.DOCUMENT)
        seen["submitted"] = await owner.ok(
            "POST",
            f"{paths['owner']}/mark-submitted",
            json={"acknowledgement": receipt, "reference": " DP-12-3456 "},
        )
        seen["too late to edit"] = (
            await student.call("PUT", paths["student"], json=_details())
        ).json()["code"]
        seen["verified"] = await owner.ok("POST", f"{paths['owner']}/mark-verified")
        seen["student sees"] = await student.ok("GET", paths["student"])
        seen["ops"] = await ops.ok("GET", paths["ops"])
        row = await _row(ops, code)
        async with ops.app.state.sessionmaker() as db:
            verification = await db.scalar(
                select(TenantVerification).where(TenantVerification.agreement_id == row.id)
            )
            assert verification is not None
            rows = await db.execute(
                select(AuditLog.action, AuditLog.actor_type, AuditLog.details)
                .where(AuditLog.entity_id == str(verification.public_id))
                .order_by(AuditLog.id)
            )
            seen["audit"] = [(action, actor, details) for action, actor, details in rows]
        return seen

    seen = run(scenario)

    read = seen["owner reads"]
    assert read["details"]["fullName"] == "Asha Verma"
    assert (read["details"]["idType"], read["details"]["idLast4"]) == ("aadhaar", "4321")
    assert read["details"]["phone"] == "+919876500001"
    assert read["tenancy"]["pgAddress"].startswith("House 1, a fictional lane")
    assert read["tenancy"]["room"] == "Bed A, room 101 (Double sharing)"
    assert (read["canMarkSubmitted"], read["canMarkVerified"]) == (True, False)
    assert seen["refused"] == ["ACKNOWLEDGEMENT_INVALID", "ACKNOWLEDGEMENT_INVALID"]
    submitted = seen["submitted"]
    assert submitted["status"] == "submitted_to_police"
    assert submitted["policeReference"] == "DP-12-3456"
    assert submitted["acknowledgement"]
    assert (submitted["canMarkSubmitted"], submitted["canMarkVerified"]) == (False, True)
    assert seen["too late to edit"] == "INVALID_TRANSITION"
    assert seen["verified"]["status"] == "verified"
    assert (seen["student sees"]["status"], seen["student sees"]["canEdit"]) == ("verified", False)
    assert seen["ops"]["details"] == read["details"]
    assert seen["ops"]["status"] == "verified"
    assert [(action, actor) for action, actor, _ in seen["audit"]] == [
        ("police_verification.details_given", "user"),
        ("police_verification.details_viewed", "owner"),
        ("police_verification.submitted", "owner"),
        ("police_verification.verified", "owner"),
        ("police_verification.details_viewed", "staff"),
    ]
    # The audit log never holds the details themselves.
    assert "Asha" not in str([details for *_, details in seen["audit"]])


def test_the_details_are_in_the_export_and_erased_after_verification(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, owner, code = await _confirmed(ops)
        paths = _paths(code)
        await student.ok("PUT", paths["student"], json=_details())
        receipt = await owner.media(purpose=Purpose.DOCUMENT)
        await owner.ok(
            "POST", f"{paths['owner']}/mark-submitted", json={"acknowledgement": receipt}
        )
        await owner.ok("POST", f"{paths['owner']}/mark-verified")
        seen: dict[str, Any] = {}
        async with ops.app.state.sessionmaker() as db:
            seen["export"] = await agreements_part(ops.app.state.field_cipher)(db, student.user_id)
        clock = ops.app.state.clock
        async with ops.app.state.sessionmaker() as db, db.begin():
            seen["too soon"] = await erase_police_details(db, clock)
        clock.advance(timedelta(days=30, minutes=1))
        async with ops.app.state.sessionmaker() as db, db.begin():
            seen["erased"] = await erase_police_details(db, clock)
        # A month on, both sign in again.
        seen["after"] = await (await _again(owner)).ok("GET", paths["owner"])
        seen["student after"] = await (await _again(student)).ok("GET", paths["student"])
        return seen

    seen = run(scenario)

    exported = seen["export"]["rentAgreements"]
    assert len(exported) == 1
    assert exported[0]["policeVerification"]["details"]["full_name"] == "Asha Verma"
    assert exported[0]["policeVerification"]["status"] == "verified"
    assert seen["too soon"] == 0
    assert seen["erased"] >= 1
    after = seen["after"]
    assert (after["status"], after["details"], after["erased"]) == ("verified", None, True)
    assert after["acknowledgement"]
    assert seen["student after"]["details"] is None


def test_nothing_moves_once_the_booking_has_ended(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, _owner, code = await _confirmed(ops)
        booking = await student.ok("GET", f"/v1/bookings/{code}")
        await student.ok(
            "POST",
            f"/v1/bookings/{code}/cancel",
            json={"refundPaise": booking["cancellation"]["refundPaise"]},
        )
        paths = _paths(code)
        return {
            "give": (await student.call("PUT", paths["student"], json=_details())).json()["code"],
            "read": await student.ok("GET", paths["student"]),
        }

    seen = run(scenario)

    assert seen["give"] == "INVALID_TRANSITION"
    assert seen["read"]["canEdit"] is False
