"""Visits end to end in the API (step 3.7, ADR 0033): a student asks with up to three times, ops
book one with a field agent, the student is texted and reminded and may now see the address, the
agent checks in at the building and records how it went, and ops see the visit log. Then the
limits, who may do what, and cancelling."""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.config import Settings
from app.core.actor import Role
from app.core.calendar import INDIA
from app.jobs import EXPORTERS
from app.modules.catalog.models import Property
from app.modules.identity.domain.sessions import SessionKind
from app.modules.identity.service import SessionService
from app.modules.visits.domain.visits import StudentVisitStatus
from app.modules.visits.models import Visit
from app.modules.visits.service import visits_part
from tests.integration.test_search import _category, _publish, _token
from tests.jobs import RecordedTexts, run_due_jobs
from tests.staff_api import NOW, Staff, run_as_staff, sign_in, spot

pytestmark = pytest.mark.integration

VISITS = "/v1/visits"


@pytest.fixture
def run(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Staff], Awaitable[Any]]) -> Any:
        settings = make_settings(database_url=database_url, redis_url=valkey_url)
        return run_as_staff(settings, scenario)

    return run_scenario


def india(day: int, hour: int, minute: int = 0) -> datetime:
    """A time in July 2027 in India; NOW is Wednesday 14 July, 3:30 pm there."""
    return datetime(2027, 7, day, hour, minute, tzinfo=INDIA)


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _about(texts: RecordedTexts, token: str) -> list[tuple[str, str, dict[str, str]]]:
    """The texts sent about this test's PG: the outbox is shared with other tests' jobs."""
    return [sent for sent in texts.sent if sent[2].get("pg", "").endswith(token)]


async def _listing(ops: Staff, token: str, name: str = "Vasant") -> dict[str, Any]:
    return await _publish(
        ops,
        name=f"{name} PG {token}",
        at=spot(400),
        categories=[_category("double", 10_000, beds=2)],
    )


async def _agent_id(ops: Staff, agent: Staff) -> str:
    agents = await ops.ok("GET", "/v1/ops/field-agents")
    me = await agent.public_id()
    return str(next(item["id"] for item in agents["items"] if item["id"] == me))


async def _again(staff: Staff) -> Staff:
    """The same staff member signed in again: staff sessions end within the day, and these
    tests move the clock a day on."""
    async with staff.app.state.sessionmaker() as db:
        session = await SessionService(db, staff.app.state.clock).start(
            staff.user_id, kind=SessionKind.STAFF, ip_address=None, user_agent=None
        )
    return Staff(staff.app, staff.client, user_id=staff.user_id, token=session.token)


def test_a_student_asks_ops_book_the_agent_checks_in_and_ops_see_the_log(  # noqa: PLR0915 - one visit's whole life, in order
    run: Callable[..., Any],
) -> None:
    token = _token()
    # Friday, more than a day ahead, so both reminders go.
    at = india(16, 11)

    async def scenario(ops: Staff) -> dict[str, Any]:
        clock = ops.app.state.clock
        texts = RecordedTexts()
        listing = await _listing(ops, token)
        slug = listing["slug"]
        student = await sign_in(ops.app, ops.client, Role.STUDENT, kind=SessionKind.USER)
        agent = await sign_in(ops.app, ops.client, Role.FIELD_AGENT)
        other = await sign_in(ops.app, ops.client, Role.FIELD_AGENT)
        contact = f"/v1/properties/{slug}/contact"
        seen: dict[str, Any] = {"hidden": (await student.call("GET", contact)).status_code}
        asked = await student.ok(
            "POST", VISITS, json={"property": slug, "starts": [iso(at), iso(india(17, 17, 30))]}
        )
        seen["asked"] = asked
        seen["ops waiting"] = await ops.ok("GET", "/v1/ops/visits", params={"status": "requested"})
        booked = await ops.ok(
            "POST",
            f"/v1/ops/visits/{asked['id']}/schedule",
            json={"at": iso(at), "agent": await _agent_id(ops, agent)},
        )
        seen["booked"] = booked
        seen["shown"] = (await student.call("GET", contact)).status_code
        await run_due_jobs(ops.app, texts=texts)
        seen["texted now"] = _about(texts, token)
        # The day before, then two hours before: the reminders.
        clock.set(at - timedelta(hours=24))
        await run_due_jobs(ops.app, texts=texts)
        clock.set(at - timedelta(hours=3))
        agent, other, ops = await _again(agent), await _again(other), await _again(ops)
        seen["too early"] = (
            await agent.call(
                "POST",
                f"/v1/field/visits/{asked['id']}/check-in",
                json={"position": spot(430), "accuracyM": 12},
            )
        ).json()["code"]
        clock.set(at - timedelta(minutes=10))
        agent, other, ops = await _again(agent), await _again(other), await _again(ops)
        await run_due_jobs(ops.app, texts=texts)
        seen["texts"] = _about(texts, token)
        seen["agent's list"] = await agent.ok("GET", "/v1/field/visits")
        seen["no outcome yet"] = (
            await agent.call(
                "POST",
                f"/v1/field/visits/{asked['id']}/outcome",
                json={"outcome": "interested"},
            )
        ).json()["code"]
        seen["not theirs"] = (
            await other.call(
                "POST",
                f"/v1/field/visits/{asked['id']}/check-in",
                json={"position": spot(430), "accuracyM": 12},
            )
        ).status_code
        seen["checked in"] = await agent.ok(
            "POST",
            f"/v1/field/visits/{asked['id']}/check-in",
            json={"position": spot(430), "accuracyM": 12},
        )
        seen["done"] = await agent.ok(
            "POST",
            f"/v1/field/visits/{asked['id']}/outcome",
            json={"outcome": "interested", "note": "Liked the double room; will decide by Friday."},
        )
        seen["log"] = await ops.ok("GET", f"/v1/ops/visits/{asked['id']}")
        seen["mine"] = await student.ok("GET", VISITS)
        seen["student phone"] = (await ops.ok("GET", f"/v1/ops/visits/{asked['id']}"))["student"][
            "phone"
        ]
        seen["slug"] = slug
        async with ops.app.state.sessionmaker() as db, db.begin():
            seen["student's export"] = await visits_part(db, student.user_id)
            seen["agent's export"] = await visits_part(db, agent.user_id)
        return seen

    seen = run(scenario)

    # The address stays hidden until a visit is booked (CLAUDE.md rule 11).
    assert (seen["hidden"], seen["shown"]) == (403, 200)
    asked = seen["asked"]
    assert asked["status"] == "requested"
    assert asked["preferredStarts"] == [iso(at), iso(india(17, 17, 30))]
    assert asked["id"] in [item["id"] for item in seen["ops waiting"]["items"]]
    booked = seen["booked"]
    assert (booked["status"], booked["scheduledAt"]) == ("scheduled", iso(at))
    assert booked["nextStatuses"] == ["cancelled", "completed", "no_show"]
    # Texted at once, then reminded the day before and two hours before; never too soon.
    phone = seen["student phone"]
    [now_text] = seen["texted now"]
    assert now_text[:2] == (phone, "visit_scheduled")
    assert now_text[2]["pg"] == f"Vasant PG {token}"
    assert now_text[2]["when"] == "Fri 16 Jul, 11:00 am"
    assert now_text[2]["address"] == "House 1, a fictional lane, Kamla Nagar"
    assert [template for _, template, _ in seen["texts"]] == [
        "visit_scheduled",
        "visit_reminder",
        "visit_reminder",
    ]
    assert seen["too early"] == "CHECK_IN_TOO_EARLY"
    assert seen["no outcome yet"] == "CHECK_IN_REQUIRED"
    assert seen["not theirs"] == 404
    assert asked["id"] in [item["id"] for item in seen["agent's list"]["items"]]
    # The visit log: the time from the server, the phone's position and how far from the building.
    check_in = seen["log"]["checkIn"]
    assert check_in["at"] == iso(at - timedelta(minutes=10))
    assert check_in["accuracyM"] == 12
    assert 25 <= check_in["distanceM"] <= 35
    assert seen["done"]["status"] == "completed"
    assert seen["log"]["outcome"] == "interested"
    assert seen["log"]["outcomeNote"].startswith("Liked the double room")
    [mine] = [item for item in seen["mine"]["items"] if item["id"] == asked["id"]]
    assert (mine["status"], mine["checkedIn"], mine["outcome"]) == ("completed", True, "interested")
    assert mine["property"] == {
        "slug": seen["slug"],
        "name": f"Vasant PG {token}",
        "locality": "Kamla Nagar",
    }
    # A person's data export (DPDP) holds the visits they asked for, and an agent's the
    # check-ins they made.
    assert visits_part in EXPORTERS
    [exported] = seen["student's export"]["visits"]
    assert (exported["id"], exported["status"], exported["outcome"]) == (
        asked["id"],
        "completed",
        "interested",
    )
    assert exported["preferredStarts"] == [
        start.astimezone(UTC).isoformat() for start in (at, india(17, 17, 30))
    ]
    assert "visitCheckIns" not in seen["student's export"]
    [made] = seen["agent's export"]["visitCheckIns"]
    assert (made["visit"], made["pg"], made["accuracyM"]) == (asked["id"], f"Vasant PG {token}", 12)
    assert set(made["position"]) == {"lat", "lng"}
    assert "visits" not in seen["agent's export"]


def test_limits_and_who_may_do_what(run: Callable[..., Any]) -> None:
    token = _token()
    starts = [iso(india(15, 11))]

    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, token)
        slug = listing["slug"]
        student = await sign_in(ops.app, ops.client, Role.STUDENT, kind=SessionKind.USER)
        someone = await sign_in(ops.app, ops.client, Role.STUDENT, kind=SessionKind.USER)
        seen: dict[str, Any] = {}
        first = await student.ok("POST", VISITS, json={"property": slug, "starts": starts})
        seen["again"] = (
            await student.call("POST", VISITS, json={"property": slug, "starts": starts})
        ).json()["code"]
        seen["bad times"] = (
            await someone.call(
                "POST", VISITS, json={"property": slug, "starts": [iso(india(15, 8))]}
            )
        ).json()
        seen["no such pg"] = (
            await someone.call(
                "POST", VISITS, json={"property": "no-such-pg-at-all", "starts": starts}
            )
        ).status_code
        seen["staff"] = (
            await ops.call("POST", VISITS, json={"property": slug, "starts": starts})
        ).status_code
        seen["not yours"] = (
            await someone.call("POST", f"{VISITS}/{first['id']}/cancel")
        ).status_code
        seen["students can't book"] = (await student.call("GET", "/v1/ops/visits")).status_code
        # Four more open visits, to PGs of any kind (drafts here), make five: the limit.
        drafts = []
        for number in range(4):
            owner = await ops.owner()
            draft = await ops.ok(
                "POST",
                "/v1/ops/properties",
                json={
                    "owner": owner["id"],
                    "locality": "kamla-nagar",
                    "name": f"Draft {number} PG {token}",
                    "addressLine": "House 3, a fictional lane",
                    "location": spot(600 + 50 * number),
                    "locationPrecision": "exact",
                    "genderPolicy": "boys",
                    "meals": "none",
                },
            )
            drafts.append(uuid.UUID(draft["id"]))
        async with ops.app.state.sessionmaker() as db, db.begin():
            others = list(
                await db.scalars(select(Property.id).where(Property.public_id.in_(drafts)))
            )
            for property_id in others:
                db.add(
                    Visit(
                        property_id=property_id,
                        student_id=student.user_id,
                        status=StudentVisitStatus.REQUESTED,
                        preferred_starts=[india(15, 11)],
                        requested_at=NOW,
                    )
                )
        second = await _listing(ops, token, name="Second")
        limited = await student.call(
            "POST", VISITS, json={"property": second["slug"], "starts": starts}
        )
        seen["limit"] = limited.json().get("code", limited.text)
        return seen

    seen = run(scenario)

    assert seen["again"] == "VISIT_EXISTS"
    assert seen["bad times"]["code"] == "VISIT_INVALID"
    assert "from 9 am to 7 pm" in seen["bad times"]["detail"]
    assert seen["no such pg"] == 404
    assert seen["staff"] == 403
    assert seen["not yours"] == 404
    assert seen["students can't book"] == 403
    assert seen["limit"] == "VISIT_LIMIT_REACHED"


def test_a_student_cancels_their_own_and_ops_cancel_a_booked_one_with_a_text(
    run: Callable[..., Any],
) -> None:
    token = _token()
    at = india(16, 12)

    async def scenario(ops: Staff) -> dict[str, Any]:
        texts = RecordedTexts()
        listing = await _listing(ops, token)
        slug = listing["slug"]
        student = await sign_in(ops.app, ops.client, Role.STUDENT, kind=SessionKind.USER)
        agent = await sign_in(ops.app, ops.client, Role.FIELD_AGENT)
        mine = await student.ok("POST", VISITS, json={"property": slug, "starts": [iso(at)]})
        cancelled = await student.ok("POST", f"{VISITS}/{mine['id']}/cancel")
        again = await student.ok("POST", VISITS, json={"property": slug, "starts": [iso(at)]})
        await ops.ok(
            "POST",
            f"/v1/ops/visits/{again['id']}/schedule",
            json={"at": iso(at), "agent": await _agent_id(ops, agent)},
        )
        # The worker texts the booking at once.
        await run_due_jobs(ops.app, texts=texts)
        dropped = await ops.ok(
            "POST", f"/v1/ops/visits/{again['id']}/cancel", json={"reason": "The owner is away."}
        )
        twice = await ops.call(
            "POST", f"/v1/ops/visits/{again['id']}/cancel", json={"reason": "Again."}
        )
        # Every reminder's time passes: none goes for a cancelled visit.
        ops.app.state.clock.set(at)
        await run_due_jobs(ops.app, texts=texts)
        return {
            "cancelled": cancelled,
            "dropped": dropped,
            "twice": twice.json()["code"],
            "texts": [template for _, template, _ in _about(texts, token)],
        }

    seen = run(scenario)

    assert (seen["cancelled"]["status"], seen["cancelled"]["cancelledBy"]) == (
        "cancelled",
        "student",
    )
    assert (seen["dropped"]["status"], seen["dropped"]["cancelReason"]) == (
        "cancelled",
        "The owner is away.",
    )
    assert seen["twice"] == "INVALID_TRANSITION"
    assert seen["texts"] == ["visit_scheduled", "visit_cancelled"]
