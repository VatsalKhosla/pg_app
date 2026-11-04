"""The bookings board in the API (step 5.10, ADR 0054): ops see every booking by status, what needs
a person now and since when, find one by its code, a student's phone or a PG's name, and read its
whole history; and they cancel for an owner and record a move-out, each with a reason."""

from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import event, select

from app.config import Settings
from app.core.audit import AuditLog
from app.core.outbox import enqueue
from app.modules.booking.jobs import CHECK_WINDOWS
from app.modules.identity.domain.sessions import SessionKind
from app.modules.inventory.models import InventoryAllocation
from tests.flags import FixedFlags
from tests.integration.test_booking_check_in import MOVED_IN, OPENS, _confirmed
from tests.integration.test_booking_confirmation import (
    _about,
    _booking,
    _held,
    _history,
    _owner_of,
    _secure,
)
from tests.integration.test_booking_disputes import REPORT
from tests.integration.test_booking_holds import _category_of, _hold, _listing, _quote, _student
from tests.integration.test_booking_student import _again
from tests.integration.test_search import _category, _publish, _token
from tests.jobs import RecordedTexts, run_due_jobs
from tests.staff_api import Staff, name_first, run_as_staff, spot

pytestmark = pytest.mark.integration

BOARD = "/v1/ops/bookings"
REASON = {"reason": "Spoke to the owner on the phone."}


@pytest.fixture
def run(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Staff], Awaitable[Any]]) -> Any:
        settings = make_settings(database_url=database_url, redis_url=valkey_url)

        async def remote_booking(ops: Staff) -> Any:
            ops.app.state.flags = FixedFlags(remote_booking_enabled=True)
            return await scenario(ops)

        return run_as_staff(settings, remote_booking)

    return run_scenario


async def _item(ops: Staff, code: str, **params: Any) -> dict[str, Any] | None:
    """The booking as the board lists it under these filters, if it does."""
    page = await ops.ok("GET", BOARD, params={"q": code, **params})
    return next((item for item in page["items"] if item["code"] == code), None)


async def _listed(ops: Staff, code: str, **params: Any) -> dict[str, Any]:
    """The booking as the board lists it, which it must."""
    found = await _item(ops, code, **params)
    assert found is not None
    return found


async def _bed(ops: Staff, code: str) -> InventoryAllocation:
    booking = await _booking(ops, code)
    async with ops.app.state.sessionmaker() as db:
        found: InventoryAllocation | None = await db.scalar(
            select(InventoryAllocation).where(InventoryAllocation.booking_id == booking.id)
        )
        assert found is not None
        return found


async def _roomy(ops: Staff, *, beds: int) -> dict[str, Any]:
    """A PG with a room of up to four beds, so several students can hold one at once."""
    return await _publish(
        ops,
        name=f"Board PG {_token()}",
        at=spot(700),
        locality="satya-niketan",
        categories=[_category("quad", 10_000, beds=beds)],
    )


async def _token_in(ops: Staff) -> str:
    """A booking at a new PG with its token in, waiting for the owner."""
    _, held = await _held(ops, await _listing(ops, beds=1))
    code: str = held["code"]
    await _secure(ops, code)
    return code


async def _active(ops: Staff) -> tuple[Staff, Staff, str]:
    """Ops signed in again, the student, and a booking settled the day after they moved in."""
    student, _, code = await _confirmed(ops)
    ops.app.state.clock.set(MOVED_IN)
    student = await _again(student)
    await student.ok("POST", f"/v1/bookings/{code}/check-in")
    ops.app.state.clock.advance(timedelta(hours=24))
    async with ops.app.state.sessionmaker() as db, db.begin():
        await enqueue(db, CHECK_WINDOWS, {}, clock=ops.app.state.clock)
    await run_due_jobs(ops.app)
    assert (await _booking(ops, code)).status == "active"
    return await _again(ops, kind=SessionKind.STAFF), student, code


def test_an_owner_past_two_hours_needs_a_person_and_the_summary_counts_them(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        code = await _token_in(ops)
        clock = ops.app.state.clock
        clock.advance(timedelta(hours=2) - timedelta(seconds=1))
        ops = await _again(ops, kind=SessionKind.STAFF)
        seen: dict[str, Any] = {
            "just before": await _item(ops, code),
            "in the attention list, just before": await _item(ops, code, attention="true"),
        }
        clock.advance(timedelta(seconds=1))
        seen["at two hours"] = await _item(ops, code, attention="true")
        before = await ops.ok("GET", f"{BOARD}/summary")
        await name_first(ops, "An ops member")
        seen["confirmed"] = (await ops.ok("POST", f"{BOARD}/{code}/confirm", json=REASON))["status"]
        after = await ops.ok("GET", f"{BOARD}/summary")
        seen["late owners"] = after["unconfirmedLate"] - before["unconfirmedLate"]
        seen["attention"] = after["attention"] - before["attention"]
        count = {entry["status"]: entry["count"] for entry in after["statuses"]}
        was = {entry["status"]: entry["count"] for entry in before["statuses"]}
        seen["moved"] = (
            count["token_secured"] - was["token_secured"],
            count["confirmed"] - was["confirmed"],
        )
        seen["read"] = await ops.ok("GET", f"{BOARD}/{code}")
        return seen

    seen = run(scenario)

    due = "2027-07-14T12:00:00Z"
    just_before = seen["just before"]
    assert just_before["timer"] == {
        "kind": "unconfirmed",
        "since": "2027-07-14T10:00:00Z",
        "due": due,
        "late": False,
    }
    assert just_before["attention"] is False
    assert seen["in the attention list, just before"] is None
    at_two = seen["at two hours"]
    assert at_two["timer"]["late"] is True
    assert at_two["attention"] is True
    assert seen["confirmed"] == "confirmed"
    assert (seen["late owners"], seen["attention"]) == (-1, -1)
    assert seen["moved"] == (-1, 1)
    # The whole history, with who did each and why.
    assert [
        (entry["event"], entry["fromStatus"], entry["toStatus"], entry["by"], entry["note"])
        for entry in seen["read"]["history"]
    ] == [
        ("hold", None, "held", "student", None),
        ("token_secured", "held", "token_secured", "system", None),
        ("confirm", "token_secured", "confirmed", "ops", REASON["reason"]),
    ]
    assert seen["read"]["history"][-1]["byName"] == "An ops member"


def test_a_dispute_is_due_by_the_end_of_its_day_and_a_move_in_on_its_own(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, _, code = await _confirmed(ops)
        clock = ops.app.state.clock
        ops = await _again(ops, kind=SessionKind.STAFF)
        seen: dict[str, Any] = {"weeks before": await _item(ops, code)}
        # Midnight in India at the start of 19 Aug: the student may say they've moved in, ops may
        # ask them to, and it's not due yet.
        clock.set(OPENS)
        ops = await _again(ops, kind=SessionKind.STAFF)
        seen["the day before"] = (await _listed(ops, code))["timer"]
        seen["its actions"] = (await ops.ok("GET", f"{BOARD}/{code}"))["actions"]
        clock.set(datetime(2027, 8, 19, 18, 30, tzinfo=UTC))
        ops = await _again(ops, kind=SessionKind.STAFF)
        seen["its day"] = await _item(ops, code, attention="true")
        clock.set(datetime(2027, 8, 20, 18, 30, tzinfo=UTC))
        ops = await _again(ops, kind=SessionKind.STAFF)
        seen["the next day"] = (await _listed(ops, code, attention="true"))["timer"]
        # They move in, and report a problem at once: 12:30 am on 21 Aug in India.
        clock.set(datetime(2027, 8, 20, 19, 0, tzinfo=UTC))
        ops = await _again(ops, kind=SessionKind.STAFF)
        student = await _again(student)
        await student.ok("POST", f"/v1/bookings/{code}/check-in")
        seen["moved in"] = (await _listed(ops, code))["timer"]
        await student.ok("POST", f"/v1/bookings/{code}/disputes", json=REPORT)
        seen["disputed"] = await _item(ops, code, attention="true")
        read = await ops.ok("GET", f"{BOARD}/{code}")
        seen["read"] = (read["dispute"]["reason"], read["dispute"]["status"], read["actions"])
        clock.set(datetime(2027, 8, 21, 18, 29, 59, tzinfo=UTC))
        ops = await _again(ops, kind=SessionKind.STAFF)
        seen["a second before"] = (await _listed(ops, code))["timer"]["late"]
        clock.advance(timedelta(seconds=1))
        seen["at midnight"] = (await _listed(ops, code))["timer"]["late"]
        return seen

    seen = run(scenario)

    assert seen["weeks before"]["timer"] is None
    assert seen["weeks before"]["attention"] is False
    assert seen["the day before"] is None
    assert seen["its actions"] == ["owner_cancel", "remind_move_in"]
    its_day = seen["its day"]
    assert its_day["attention"] is True
    assert its_day["timer"] == {
        "kind": "move_in",
        "since": "2027-08-19T18:30:00Z",
        "due": "2027-08-20T18:30:00Z",
        "late": False,
    }
    assert seen["the next day"]["late"] is True
    assert seen["moved in"] is None
    disputed = seen["disputed"]
    assert disputed["attention"] is True
    assert disputed["timer"] == {
        "kind": "dispute",
        "since": "2027-08-20T19:00:00Z",
        "due": "2027-08-21T18:30:00Z",
        "late": False,
    }
    assert seen["read"] == ("not_as_shown", "open", [])
    assert (seen["a second before"], seen["at midnight"]) == (False, True)


def test_ops_find_a_booking_by_its_code_a_phone_or_a_pgs_name(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _roomy(ops, beds=3)
        students = [await _student(ops) for _ in range(3)]
        codes = []
        for student in students:
            response = await _hold(student, (await _quote(student, _category_of(listing)))["id"])
            codes.append(response.json()["code"])

        async def named(**params: Any) -> list[str]:
            page = await ops.ok("GET", BOARD, params={"q": listing["name"], **params})
            return [item["code"] for item in page["items"]]

        phone = (await ops.ok("GET", f"{BOARD}/{codes[1]}"))["studentContact"]["phone"]
        by_phone = await ops.ok("GET", BOARD, params={"q": phone})
        one_page = await ops.ok(
            "GET", BOARD, params={"q": listing["name"], "status": "held", "limit": 2}
        )
        next_page = await ops.ok(
            "GET",
            BOARD,
            params={
                "q": listing["name"],
                "status": "held",
                "limit": 2,
                "cursor": one_page["nextCursor"],
            },
        )
        await students[0].ok("POST", f"/v1/bookings/{codes[0]}/cancel", json={"refundPaise": 0})
        await students[1].ok("POST", f"/v1/bookings/{codes[1]}/cancel", json={"refundPaise": 0})
        return {
            "codes": codes,
            "by code": [
                item["code"]
                for item in (await ops.ok("GET", BOARD, params={"q": codes[2].lower()}))["items"]
            ],
            "by phone": [item["code"] for item in by_phone["items"]],
            "by a phone nobody has": (await ops.ok("GET", BOARD, params={"q": "+919000000001"}))[
                "items"
            ],
            "by name, part of it, any case": await named(),
            "queue, oldest first": [item["code"] for item in one_page["items"]],
            "the rest": [item["code"] for item in next_page["items"]],
            "last page": next_page["nextCursor"],
            "ended, newest first": await named(status="cancelled"),
            "another channel": await named(channel="on_spot"),
            "this channel": await named(channel="remote", status="held"),
            "a bad status": (await ops.call("GET", BOARD, params={"status": "lost"})).status_code,
            "item": (await ops.ok("GET", BOARD, params={"q": codes[2]}))["items"][0],
        }

    seen = run(scenario)

    codes = seen["codes"]
    assert seen["by code"] == [codes[2]]
    assert seen["by phone"] == [codes[1]]
    assert seen["by a phone nobody has"] == []
    assert sorted(seen["by name, part of it, any case"]) == sorted(codes)
    assert seen["queue, oldest first"] == codes[:2]
    assert seen["the rest"] == codes[2:]
    assert seen["last page"] is None
    assert seen["ended, newest first"] == [codes[1], codes[0]]
    assert seen["another channel"] == []
    assert seen["this channel"] == [codes[2]]
    assert seen["a bad status"] == 422
    item = seen["item"]
    assert (item["status"], item["channel"], item["roomType"]) == (
        "held",
        "remote",
        "Quad sharing",
    )
    assert item["property"]["locality"] == "Satya Niketan"


def test_the_board_reads_in_the_same_number_of_queries_however_many(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> tuple[int, int]:
        listing = await _roomy(ops, beds=4)
        statements = 0

        def count(*_: object) -> None:
            nonlocal statements
            statements += 1

        async def read() -> int:
            nonlocal statements
            statements = 0
            event.listen(ops.app.state.engine.sync_engine, "before_cursor_execute", count)
            try:
                page = await ops.ok("GET", BOARD, params={"q": listing["name"]})
            finally:
                event.remove(ops.app.state.engine.sync_engine, "before_cursor_execute", count)
            assert page["items"]
            return statements

        async def reserve() -> None:
            student = await _student(ops)
            quote = await _quote(student, _category_of(listing))
            assert (await _hold(student, quote["id"])).status_code == 201

        await reserve()
        few = await read()
        for _ in range(3):
            await reserve()
        return few, await read()

    few, many = run(scenario)

    assert few == many


def test_a_booking_page_says_whom_to_call_and_what_the_booking_is_worth(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, beds=1)
        owner = await _owner_of(ops, listing)
        student, held = await _held(ops, listing)
        await name_first(student, "Asha Fictional")
        read = await ops.ok("GET", f"{BOARD}/{held['code']}")
        booking = await _booking(ops, held["code"])
        return {
            "read": read,
            "owner": listing["owner"]["phone"],
            "stored": (
                booking.fee_paise,
                booking.gst_paise,
                booking.owner_fee_total_paise,
                booking.monthly_charges_paise,
                booking.one_time_charges_paise,
            ),
            "owner's view": await owner.ok("GET", f"/v1/owner/bookings/{held['code']}"),
        }

    seen = run(scenario)

    read = seen["read"]
    assert read["studentContact"]["name"] == "Asha Fictional"
    assert read["studentContact"]["phone"].startswith("+91")
    assert read["ownerContact"]["phone"].endswith(seen["owner"][-10:])
    assert read["student"] == {"name": "Asha"}
    assert (
        read["feePaise"],
        read["gstPaise"],
        read["ownerFeeTotalPaise"],
        read["monthlyChargesPaise"],
        read["oneTimeChargesPaise"],
    ) == seen["stored"]
    assert (read["visit"], read["dispute"], read["ownerCancellations"]) == (None, None, 0)
    assert read["actions"] == []
    # The owner gets none of ops' own: no student's phone, no history, no fee breakdown.
    for field in ("studentContact", "history", "actions", "feePaise"):
        assert field not in seen["owner's view"]


def test_ops_cancel_for_an_owner_freeing_the_bed_and_counting_it_against_them(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, beds=2)
        student, held = await _held(ops, listing)
        code = held["code"]
        cancel = f"{BOARD}/{code}/owner-cancel"
        seen: dict[str, Any] = {
            "held": (await ops.call("POST", cancel, json=REASON)).json()["code"],
            "no reason": (await ops.call("POST", cancel, json={})).status_code,
        }
        await _secure(ops, code)
        await run_due_jobs(ops.app)
        seen["cancelled"] = (await ops.ok("POST", cancel, json=REASON))["status"]
        seen["again"] = (await ops.call("POST", cancel, json=REASON)).json()["code"]
        texts = RecordedTexts()
        await run_due_jobs(ops.app, texts=texts)
        seen["texts"] = sorted(template for template, _ in _about(texts, code))
        seen["bed held"] = (await _bed(ops, code)).is_active
        booking = await _booking(ops, code)
        seen["ended"] = (booking.cancelled_by, booking.cancellation_kind)
        seen["history"] = (await _history(ops, code))[-1]
        seen["student sees"] = await student.ok("GET", f"/v1/bookings/{code}")
        read = await ops.ok("GET", f"{BOARD}/{code}")
        seen["count"] = read["ownerCancellations"]
        seen["note"] = read["history"][-1]["note"]
        async with ops.app.state.sessionmaker() as db:
            seen["audit"] = await db.scalar(
                select(AuditLog.details["note"].astext).where(
                    AuditLog.entity_id == code, AuditLog.action == "booking.owner_cancel"
                )
            )
        return seen

    seen = run(scenario)

    assert seen["held"] == "INVALID_TRANSITION"
    assert seen["no reason"] == 422
    assert seen["cancelled"] == "cancelled"
    assert seen["again"] == "INVALID_TRANSITION"
    assert seen["texts"] == ["booking_owner_cancelled"]
    assert seen["bed held"] is False
    assert seen["ended"] == ("ops", "owner_cancel")
    assert seen["history"] == ("owner_cancel", "ops")
    assert seen["student sees"]["status"] == "cancelled"
    # Help to book again, as a rejection gives.
    assert seen["student sees"]["rebook"]["moveInMonth"] == "2027-08"
    assert seen["count"] == 1
    assert seen["note"] == REASON["reason"]
    assert seen["audit"] == REASON["reason"]


def test_a_move_out_ends_the_booking_and_frees_the_bed_from_that_day(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        ops, _, code = await _active(ops)
        clock = ops.app.state.clock
        move_out = f"{BOARD}/{code}/move-out"

        async def refused(on: str) -> tuple[int, str]:
            response = await ops.call("POST", move_out, json={"movedOutOn": on, **REASON})
            return response.status_code, response.json()["detail"]

        seen: dict[str, Any] = {
            "on the move-in day": await refused("2027-08-20"),
            "still to come": await refused("2027-09-30"),
            "offered": (await ops.ok("GET", f"{BOARD}/{code}"))["actions"],
        }
        clock.set(datetime(2027, 12, 1, 6, 0, tzinfo=UTC))
        ops = await _again(ops, kind=SessionKind.STAFF)
        seen["done"] = (
            await ops.ok("POST", move_out, json={"movedOutOn": "2027-11-30", **REASON})
        )["status"]
        booking = await _booking(ops, code)
        seen["stored"] = (booking.moved_out_on, booking.completed_at)
        bed = await _bed(ops, code)
        seen["bed"] = (bed.is_active, bed.period.lower, bed.period.upper)
        read = await ops.ok("GET", f"{BOARD}/{code}")
        seen["read"] = (read["movedOutOn"], read["actions"], read["history"][-1]["note"])
        seen["again"] = (
            await ops.call("POST", move_out, json={"movedOutOn": "2027-11-30", **REASON})
        ).json()["code"]
        return seen

    seen = run(scenario)

    assert seen["on the move-in day"] == (409, "A move-out comes after the move-in.")
    assert seen["still to come"] == (409, "A move-out is recorded once it has happened.")
    assert seen["done"] == "completed"
    assert seen["stored"] == (date(2027, 11, 30), datetime(2027, 12, 1, 6, 0, tzinfo=UTC))
    # Still a stay that happened, ending that day: the bed is free from then.
    assert seen["bed"] == (True, date(2027, 8, 20), date(2027, 11, 30))
    assert seen["read"] == ("2027-11-30", [], REASON["reason"])
    assert seen["again"] == "INVALID_TRANSITION"


def test_a_stay_past_its_planned_end_keeps_the_beds_planned_days(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        ops, _, code = await _active(ops)
        planned = (await _booking(ops, code)).planned_move_out
        # A month past the planned end, when another booking may hold the bed.
        ops.app.state.clock.set(
            datetime.combine(planned, datetime.min.time(), tzinfo=UTC) + timedelta(days=31)
        )
        ops = await _again(ops, kind=SessionKind.STAFF)
        on = planned + timedelta(days=30)
        await ops.ok("POST", f"{BOARD}/{code}/move-out", json={"movedOutOn": str(on), **REASON})
        bed = await _bed(ops, code)
        return {
            "bed ends": bed.period.upper,
            "planned": planned,
            "moved out": (await _booking(ops, code)).moved_out_on,
            "on": on,
        }

    seen = run(scenario)

    assert seen["bed ends"] == seen["planned"]
    assert seen["moved out"] == seen["on"]


def test_ops_confirming_for_an_owner_say_why(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        code = await _token_in(ops)
        confirm = f"{BOARD}/{code}/confirm"
        return {
            "no body": (await ops.call("POST", confirm)).status_code,
            "blank": (await ops.call("POST", confirm, json={"reason": ""})).status_code,
            "extra": (await ops.call("POST", confirm, json={**REASON, "paidPaise": 1})).status_code,
            "said": (await ops.ok("POST", confirm, json=REASON))["status"],
        }

    assert run(scenario) == {"no body": 422, "blank": 422, "extra": 422, "said": "confirmed"}
