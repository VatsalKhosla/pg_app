"""Rent agreements in the API and the database (ADR 0070):
- once the owner confirms a booking, the student and the owner each sign the same text, with a
  code each and their name typed, and the record keeps who, when, from where and the text's hash;
- a wrong code counts and five lock it; an expired one is refused; a text that changed is refused;
- the agreement is void when the booking is cancelled before both have signed;
- nobody sees another person's agreement;
- the database itself keeps signatures and signed texts as they are.
"""

import secrets
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.config import Settings
from app.core.actor import Role
from app.core.audit import AuditLog
from app.core.money import format_rupees
from app.modules.agreements.models import AgreementSignature, RentalAgreement
from app.modules.booking.models import Booking
from app.modules.identity.domain.sessions import SessionKind
from app.modules.identity.repository import UserRepository
from tests.flags import FixedFlags
from tests.integration.test_booking_confirmation import _held, _owner_of, _secure
from tests.integration.test_booking_holds import _listing
from tests.jobs import run_due_jobs
from tests.staff_api import NOW, Staff, name_first, run_as_staff, sign_in

pytestmark = pytest.mark.integration

SIGNED = "signed_by_student"


# The address each person in these tests signs with, by account.
_EMAILS: dict[int, str] = {}


class RecordedCodes:
    """The signing codes the port was asked to email, as (address, code), in order. Nothing is
    shown on screen, as wherever email really goes."""

    shows_code = False

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send(self, to: str, code: str) -> None:
        self.sent.append((to, code))

    def last(self, person: Staff) -> str:
        email = _EMAILS[person.user_id]
        return next(code for to, code in reversed(self.sent) if to == email)


async def give_email(person: Staff) -> str:
    """An address on this person's account, as a sign-in by email leaves one (ADR 0068)."""
    email = f"{secrets.token_hex(6)}@example.com"
    async with person.app.state.sessionmaker() as db, db.begin():
        user = await UserRepository(db).get(person.user_id)
        assert user is not None
        user.email = email
    _EMAILS[person.user_id] = email
    return email


@pytest.fixture
def run(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Staff, RecordedCodes], Awaitable[Any]]) -> Any:
        settings = make_settings(database_url=database_url, redis_url=valkey_url)

        async def prepared(ops: Staff) -> Any:
            ops.app.state.flags = FixedFlags(remote_booking_enabled=True)
            codes = RecordedCodes()
            ops.app.state.signing_code_sender = codes
            return await scenario(ops, codes)

        return run_as_staff(settings, prepared)

    return run_scenario


async def _confirmed(ops: Staff, *, name: str | None = "Asha Verma") -> tuple[Staff, Staff, str]:
    """A student with a booking its owner has confirmed, and the owner, signed in."""
    listing = await _listing(ops, beds=1)
    owner = await _owner_of(ops, listing)
    student, held = await _held(ops, listing)
    if name is not None:
        await name_first(student, name)
    await give_email(student)
    await give_email(owner)
    code = held["code"]
    await _secure(ops, code)
    await owner.ok("POST", f"/v1/owner/bookings/{code}/confirm")
    return student, owner, code


def _paths(code: str) -> dict[str, str]:
    return {
        "student": f"/v1/bookings/{code}/agreement",
        "owner": f"/v1/owner/bookings/{code}/agreement",
        "ops": f"/v1/ops/bookings/{code}/agreement",
    }


async def _sign(
    person: Staff, path: str, codes: RecordedCodes, *, name: str, sha: str | None = None
) -> dict[str, Any]:
    sent = await person.call("POST", f"{path}/signing-codes")
    assert sent.status_code == 202, sent.text
    agreement = await person.ok("GET", path)
    return await person.ok(
        "POST",
        f"{path}/signatures",
        json={
            "code": codes.last(person),
            "fullName": name,
            "textSha256": sha or agreement["textSha256"],
        },
    )


async def _row(ops: Staff, code: str) -> RentalAgreement:
    async with ops.app.state.sessionmaker() as db:
        found: RentalAgreement | None = await db.scalar(
            select(RentalAgreement)
            .join(Booking, Booking.id == RentalAgreement.booking_id)
            .where(Booking.code == code)
        )
        assert found is not None
        return found


async def _audit(ops: Staff, entity_id: str) -> list[tuple[str, str]]:
    async with ops.app.state.sessionmaker() as db:
        rows = await db.execute(
            select(AuditLog.action, AuditLog.actor_type)
            .where(AuditLog.entity_id == entity_id)
            .order_by(AuditLog.id)
        )
        return [(action, actor) for action, actor in rows]


def test_both_sides_sign_the_same_text_with_a_code_each(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff, codes: RecordedCodes) -> dict[str, Any]:
        student, owner, code = await _confirmed(ops)
        paths = _paths(code)
        seen: dict[str, Any] = {"booking": await student.ok("GET", f"/v1/bookings/{code}")}
        # Before the job has run, the agreement is there to read all the same.
        seen["before the job"] = await ops.ok("GET", paths["ops"])
        await run_due_jobs(ops.app)
        seen["student reads"] = await student.ok("GET", paths["student"])
        seen["owner reads"] = await owner.ok("GET", paths["owner"])
        seen["student signs"] = await _sign(student, paths["student"], codes, name=" Asha  Verma ")
        # Once anyone has signed, the text is settled: a new name changes nothing in it.
        await name_first(student, "Asha Renamed")
        seen["owner reads again"] = await owner.ok("GET", paths["owner"])
        seen["owner signs"] = await _sign(owner, paths["owner"], codes, name="A Fictional Owner")
        seen["student again"] = (
            await student.call("POST", f"{paths['student']}/signing-codes")
        ).json()
        seen["ops"] = await ops.ok("GET", paths["ops"])
        seen |= {
            "codes": [to for to, _ in codes.sent],
            "emails": [_EMAILS[student.user_id], _EMAILS[owner.user_id]],
            "people": [student.user_id, owner.user_id],
        }
        row = await _row(ops, code)
        seen["audit"] = await _audit(ops, str(row.public_id))
        async with ops.app.state.sessionmaker() as db:
            signatures = list(
                await db.scalars(
                    select(AgreementSignature).where(AgreementSignature.agreement_id == row.id)
                )
            )
        seen["signatures"] = [(each.signer, each.user_id, each.typed_name) for each in signatures]
        return seen

    seen = run(scenario)

    before = seen["before the job"]
    assert (before["status"], before["createdAt"], before["signatures"]) == (
        "awaiting_signatures",
        None,
        [],
    )
    read = seen["student reads"]
    assert read["status"] == "awaiting_signatures"
    assert read["you"] == "student"
    assert read["draft"] is True
    assert (read["ready"], read["missing"], read["canSign"]) == (True, [], True)
    assert read["textSha256"] == seen["owner reads"]["textSha256"] == before["textSha256"]
    assert read["text"].startswith("# Leave and licence agreement")
    assert "**DRAFT" in read["text"]
    booking = seen["booking"]
    for fact in (
        "Asha Verma",
        "Fictional Stays Private Limited",
        "House 1, a fictional lane",
        booking["code"],
        "20 August 2027",
        format_rupees(booking["monthlyRentPaise"]),
        format_rupees(booking["depositPaise"]),
        format_rupees(booking["tokenPaise"]),
    ):
        assert fact in read["text"], fact

    by_student = seen["student signs"]
    assert (by_student["status"], by_student["canSign"]) == (SIGNED, False)
    assert by_student["signatures"] == [
        {"signer": "student", "name": "Asha Verma", "signedAt": "2027-07-14T10:00:00Z"}
    ]
    assert seen["owner reads again"]["textSha256"] == read["textSha256"]
    assert seen["owner reads again"]["canSign"] is True
    both = seen["owner signs"]
    assert both["status"] == "signed"
    assert both["signedAt"] == NOW.isoformat().replace("+00:00", "Z")
    assert [signature["signer"] for signature in both["signatures"]] == ["student", "owner"]
    assert seen["student again"]["code"] == "INVALID_TRANSITION"
    evidence = seen["ops"]["signatures"]
    assert {each["textSha256"] for each in evidence} == {read["textSha256"]}
    assert all(each["ipAddress"] and each["templateVersion"] == "draft-1" for each in evidence)
    # Each code went to the signer's own address, and nowhere else.
    assert seen["codes"] == seen["emails"]
    assert seen["signatures"] == [
        ("student", seen["people"][0], "Asha Verma"),
        ("owner", seen["people"][1], "A Fictional Owner"),
    ]
    assert seen["audit"] == [
        ("agreement.created", "system"),
        ("agreement.signed", "user"),
        ("agreement.signed", "owner"),
    ]


def test_the_database_keeps_signatures_and_signed_texts_as_they_are(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff, codes: RecordedCodes) -> list[str]:
        student, _owner, code = await _confirmed(ops)
        await _sign(student, _paths(code)["student"], codes, name="Asha Verma")
        row = await _row(ops, code)
        refused = []
        for statement in (
            "UPDATE agreement_signatures SET typed_name = 'Someone Else' WHERE agreement_id = :id",
            "DELETE FROM agreement_signatures WHERE agreement_id = :id",
            # A new text, with its own correct hash: the signature names the old one.
            "UPDATE rental_agreements SET text = text || ' ',"
            " text_sha256 = encode(sha256(convert_to(text || ' ', 'UTF8')), 'hex') WHERE id = :id",
            # A new text with the old hash.
            "UPDATE rental_agreements SET text = text || ' ' WHERE id = :id",
        ):
            async with ops.app.state.sessionmaker() as db:
                try:
                    async with db.begin():
                        await db.execute(text(statement), {"id": row.id})
                except DBAPIError as error:
                    refused.append(type(error.orig).__name__ if error.orig else "refused")
        return refused

    assert len(run(scenario)) == 4


def test_a_wrong_code_counts_and_five_lock_it(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff, codes: RecordedCodes) -> dict[str, Any]:
        student, _owner, code = await _confirmed(ops)
        path = _paths(code)["student"]
        assert (await student.call("POST", f"{path}/signing-codes")).status_code == 202
        right = codes.last(student)
        wrong = "000000" if right != "000000" else "111111"
        sha = (await student.ok("GET", path))["textSha256"]
        body = {"code": wrong, "fullName": "Asha Verma", "textSha256": sha}
        answers = []
        for _ in range(5):
            response = await student.call("POST", f"{path}/signatures", json=body)
            answers.append(
                (response.status_code, response.json()["code"], response.json()["detail"])
            )
        locked = await student.call("POST", f"{path}/signatures", json=body | {"code": right})
        too_soon = await student.call("POST", f"{path}/signing-codes")
        ops.app.state.clock.advance(timedelta(seconds=31))
        again = await student.call("POST", f"{path}/signing-codes")
        signed = await student.call(
            "POST", f"{path}/signatures", json=body | {"code": codes.last(student)}
        )
        return {
            "answers": answers,
            "locked": locked.json()["code"],
            "too soon": (
                too_soon.status_code,
                too_soon.json()["code"],
                too_soon.headers["retry-after"],
            ),
            "again": again.status_code,
            "signed": signed.json()["status"],
        }

    seen = run(scenario)

    assert [(status, code) for status, code, _ in seen["answers"]] == [
        (400, "SIGNING_CODE_INVALID")
    ] * 5
    assert seen["answers"][0][2] == "4 attempts left."
    assert seen["answers"][4][2] == "No attempts left; ask for a new code."
    assert seen["locked"] == "SIGNING_CODE_LOCKED"
    assert seen["too soon"] == (429, "SIGNING_CODE_TOO_SOON", "30")
    assert (seen["again"], seen["signed"]) == (202, SIGNED)


def test_an_expired_code_is_refused(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff, codes: RecordedCodes) -> tuple[str, str]:
        student, _owner, code = await _confirmed(ops)
        path = _paths(code)["student"]
        sent = (await student.call("POST", f"{path}/signing-codes")).json()
        sha = (await student.ok("GET", path))["textSha256"]
        ops.app.state.clock.advance(timedelta(minutes=10))
        response = await student.call(
            "POST",
            f"{path}/signatures",
            json={"code": codes.last(student), "fullName": "Asha Verma", "textSha256": sha},
        )
        return sent["expiresAt"], response.json()["code"]

    expires_at, refused = run(scenario)

    assert expires_at == (NOW + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    assert refused == "SIGNING_CODE_EXPIRED"


def test_a_text_that_changed_since_it_was_read_is_refused_and_the_code_kept(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff, codes: RecordedCodes) -> dict[str, Any]:
        student, _owner, code = await _confirmed(ops)
        path = _paths(code)["student"]
        assert (await student.call("POST", f"{path}/signing-codes")).status_code == 202
        read = await student.ok("GET", path)
        # The student corrects their name: nobody has signed, so the text follows.
        await name_first(student, "Asha Kumari Verma")
        body = {"code": codes.last(student), "fullName": "Asha Kumari Verma"}
        stale = await student.call(
            "POST", f"{path}/signatures", json=body | {"textSha256": read["textSha256"]}
        )
        reread = await student.ok("GET", path)
        signed = await student.ok(
            "POST", f"{path}/signatures", json=body | {"textSha256": reread["textSha256"]}
        )
        return {"stale": stale.json()["code"], "read": read, "reread": reread, "signed": signed}

    seen = run(scenario)

    assert seen["stale"] == "AGREEMENT_TEXT_CHANGED"
    assert seen["reread"]["textSha256"] != seen["read"]["textSha256"]
    assert "Asha Kumari Verma" in seen["reread"]["text"]
    assert seen["signed"]["status"] == SIGNED


def test_nobody_signs_before_the_student_has_a_name(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff, _codes: RecordedCodes) -> dict[str, Any]:
        student, owner, code = await _confirmed(ops, name=None)
        paths = _paths(code)
        return {
            "read": await student.ok("GET", paths["student"]),
            "student": (await student.call("POST", f"{paths['student']}/signing-codes")).json(),
            "owner": (await owner.call("POST", f"{paths['owner']}/signing-codes")).json(),
        }

    seen = run(scenario)

    assert (seen["read"]["ready"], seen["read"]["canSign"]) == (False, False)
    assert seen["read"]["missing"] == ["the student's name"]
    assert "[the student's full name" in seen["read"]["text"]
    assert seen["student"]["code"] == seen["owner"]["code"] == "AGREEMENT_NOT_READY"


def test_cancelling_the_booking_before_both_sign_voids_the_agreement(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff, codes: RecordedCodes) -> dict[str, Any]:
        student, owner, code = await _confirmed(ops)
        paths = _paths(code)
        await run_due_jobs(ops.app)
        await _sign(student, paths["student"], codes, name="Asha Verma")
        booking = await student.ok("GET", f"/v1/bookings/{code}")
        await student.ok(
            "POST",
            f"/v1/bookings/{code}/cancel",
            json={"refundPaise": booking["cancellation"]["refundPaise"]},
        )
        seen: dict[str, Any] = {"before the job": await owner.ok("GET", paths["owner"])}
        await run_due_jobs(ops.app)
        seen["after"] = await owner.ok("GET", paths["owner"])
        seen["ops"] = await ops.ok("GET", paths["ops"])
        seen["owner signs"] = (await owner.call("POST", f"{paths['owner']}/signing-codes")).json()
        seen["audit"] = await _audit(ops, str((await _row(ops, code)).public_id))
        return seen

    seen = run(scenario)

    # The booking's end shows at once; the job then writes it down.
    assert seen["before the job"]["status"] == "void"
    assert seen["after"]["status"] == "void"
    assert seen["after"]["canSign"] is False
    assert seen["ops"]["voidedAt"] is not None
    assert seen["ops"]["bookingEndedAt"] is not None
    # The student's signature stays on the record.
    assert [each["signer"] for each in seen["ops"]["signatures"]] == ["student"]
    assert seen["owner signs"]["code"] == "INVALID_TRANSITION"
    assert ("agreement.void", "system") in seen["audit"]


def test_nobody_sees_another_persons_agreement(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff, _codes: RecordedCodes) -> dict[str, int]:
        student, _owner, code = await _confirmed(ops)
        paths = _paths(code)
        stranger = await sign_in(ops.app, ops.client, Role.STUDENT, kind=SessionKind.USER)
        other_owner = await _owner_of(ops, await _listing(ops, beds=1))
        # A booking the owner hasn't confirmed has no agreement yet.
        listing = await _listing(ops, beds=1)
        waiting_student, waiting = await _held(ops, listing)
        waiting_path = _paths(waiting["code"])["student"]
        return {
            "stranger": (await stranger.call("GET", paths["student"])).status_code,
            "stranger signs": (
                await stranger.call("POST", f"{paths['student']}/signing-codes")
            ).status_code,
            "stranger police": (
                await stranger.call("GET", f"/v1/bookings/{code}/police-verification")
            ).status_code,
            "other owner": (await other_owner.call("GET", paths["owner"])).status_code,
            "other owner police": (
                await other_owner.call("GET", f"/v1/owner/bookings/{code}/police-verification")
            ).status_code,
            "student as owner": (await student.call("GET", paths["owner"])).status_code,
            "not confirmed": (await waiting_student.call("GET", waiting_path)).status_code,
        }

    assert run(scenario) == {
        "stranger": 404,
        "stranger signs": 404,
        "stranger police": 404,
        "other owner": 404,
        "other owner police": 404,
        "student as owner": 403,
        "not confirmed": 404,
    }


def test_a_signer_without_an_email_address_is_told_so(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff, codes: RecordedCodes) -> dict[str, Any]:
        student, _owner, code = await _confirmed(ops)
        async with ops.app.state.sessionmaker() as db, db.begin():
            user = await UserRepository(db).get(student.user_id)
            assert user is not None
            user.email = None
        path = _paths(code)["student"]
        refused = await student.call("POST", f"{path}/signing-codes")
        # A test site without email shows the code on screen instead, as it does sign-in codes.
        codes.shows_code = True
        shown = await student.call("POST", f"{path}/signing-codes")
        return {"refused": refused.json()["code"], "shown": shown.json(), "sent": codes.sent}

    seen = run(scenario)

    assert seen["refused"] == "SIGNING_NEEDS_EMAIL"
    assert seen["shown"]["developmentCode"] is not None
    assert seen["sent"] == []
