"""Reserving on the spot (step 5.9, ADR 0053): at their visit, once the agent has checked in at
the PG, the student reserves a bed there from their own phone, while remote booking is still
off. The booking is made on the spot and linked to the visit, whose log shows it."""

import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.config import Settings
from app.core.actor import Role
from app.modules.booking.models import Booking
from app.modules.identity.domain.sessions import SessionKind
from app.modules.visits.models import Visit
from tests.flags import FixedFlags
from tests.integration.test_booking_holds import HOLDS, _category_of, _quote
from tests.integration.test_booking_student import _again
from tests.integration.test_search import _category, _publish, _token
from tests.integration.test_visits import VISITS, _agent_id, india, iso
from tests.staff_api import Staff, run_as_staff, sign_in, spot

pytestmark = pytest.mark.integration

# Friday 16 July, 11 am in India: the visit.
AT = india(16, 11)


@pytest.fixture
def run(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Staff], Awaitable[Any]]) -> Any:
        settings = make_settings(database_url=database_url, redis_url=valkey_url)

        async def visit_first(ops: Staff) -> Any:
            # Season one: beds are reserved on visits, and remote booking stays off.
            ops.app.state.flags = FixedFlags(remote_booking_enabled=False)
            return await scenario(ops)

        return run_as_staff(settings, visit_first)

    return run_scenario


async def _listing(ops: Staff) -> dict[str, Any]:
    return await _publish(
        ops,
        name=f"On-spot PG {_token()}",
        at=spot(400),
        categories=[_category("double", 10_000, beds=2)],
    )


async def _visit(ops: Staff, student: Staff, agent: Staff, listing: dict[str, Any]) -> str:
    """The student's visit to ``listing`` at AT, booked with ``agent``."""
    asked = await student.ok(
        "POST", VISITS, json={"property": listing["slug"], "starts": [iso(AT)]}
    )
    await ops.ok(
        "POST",
        f"/v1/ops/visits/{asked['id']}/schedule",
        json={"at": iso(AT), "agent": await _agent_id(ops, agent)},
    )
    return str(asked["id"])


async def _check_in(agent: Staff, visit: str) -> None:
    await agent.ok(
        "POST",
        f"/v1/field/visits/{visit}/check-in",
        json={"position": spot(430), "accuracyM": 12},
    )


async def _reserve(student: Staff, quote: str, visit: str | None) -> Any:
    body = {"quote": quote} if visit is None else {"quote": quote, "visit": visit}
    return await student.call(
        "POST", HOLDS, json=body, headers={"Idempotency-Key": f"hold-{uuid.uuid4().hex}"}
    )


def _mine(visits: dict[str, Any], visit: str) -> dict[str, Any]:
    found: dict[str, Any] = next(item for item in visits["items"] if item["id"] == visit)
    return found


def test_a_student_reserves_on_the_spot_and_the_visit_log_links_the_booking(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops)
        student = await sign_in(ops.app, ops.client, Role.STUDENT, kind=SessionKind.USER)
        agent = await sign_in(ops.app, ops.client, Role.FIELD_AGENT)
        visit = await _visit(ops, student, agent, listing)
        ops.app.state.clock.set(AT - timedelta(minutes=10))
        ops = await _again(ops, kind=SessionKind.STAFF)
        agent = await _again(agent, kind=SessionKind.STAFF)
        student = await _again(student)
        quote = (await _quote(student, _category_of(listing)))["id"]
        seen: dict[str, Any] = {
            "before check-in": _mine(await student.ok("GET", VISITS), visit)["canReserve"]
        }
        early = await _reserve(student, quote, visit)
        seen["too soon"] = (early.status_code, early.json()["code"], early.json()["detail"])
        await _check_in(agent, visit)
        seen["checked in"] = _mine(await student.ok("GET", VISITS), visit)["canReserve"]
        seen["without the visit"] = (await _reserve(student, quote, None)).json()["code"]
        reserved = await _reserve(student, quote, visit)
        assert reserved.status_code == 201, reserved.text
        booking = reserved.json()
        seen["booking"] = (booking["status"], booking["channel"])
        code = booking["code"]
        seen["ops' log"] = (await ops.ok("GET", f"/v1/ops/visits/{visit}"))["booking"]
        mine = _mine(await student.ok("GET", VISITS), visit)
        seen["student's visit"] = mine["booking"]
        seen["ops' booking"] = (await ops.ok("GET", f"/v1/ops/bookings/{code}"))["channel"]
        async with ops.app.state.sessionmaker() as db:
            stored = await db.scalar(select(Booking).where(Booking.code == code))
            linked = await db.scalar(select(Visit.public_id).where(Visit.id == stored.visit_id))
        seen["linked"] = str(linked) == visit
        seen["code"] = code
        return seen

    seen = run(scenario)

    assert seen["before check-in"] is False
    assert seen["too soon"] == (
        409,
        "VISIT_NOT_ON_SITE",
        "The agent hasn't checked in at the PG for this visit yet.",
    )
    assert seen["checked in"] is True
    assert seen["without the visit"] == "BOOKING_NEEDS_VISIT"
    assert seen["booking"] == ("held", "on_spot")
    assert seen["ops' log"] == seen["code"]
    assert seen["student's visit"] == seen["code"]
    assert seen["ops' booking"] == "on_spot"
    assert seen["linked"] is True


def test_on_the_spot_takes_the_students_own_visit_to_that_pg_on_its_day(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing, elsewhere = await _listing(ops), await _listing(ops)
        student = await sign_in(ops.app, ops.client, Role.STUDENT, kind=SessionKind.USER)
        other = await sign_in(ops.app, ops.client, Role.STUDENT, kind=SessionKind.USER)
        agent = await sign_in(ops.app, ops.client, Role.FIELD_AGENT)
        visit = await _visit(ops, student, agent, listing)
        ops.app.state.clock.set(AT - timedelta(minutes=10))
        agent = await _again(agent, kind=SessionKind.STAFF)
        await _check_in(agent, visit)
        student, other = await _again(student), await _again(other)
        seen: dict[str, Any] = {
            "someone else's": (
                await _reserve(other, (await _quote(other, _category_of(listing)))["id"], visit)
            ).status_code
        }
        wrong = await _reserve(
            student, (await _quote(student, _category_of(elsewhere)))["id"], visit
        )
        seen["another PG"] = (wrong.json()["code"], wrong.json()["detail"])
        # The next morning in India, the visit's day is over.
        ops.app.state.clock.set(india(17, 9))
        student = await _again(student)
        seen["next day"] = _mine(await student.ok("GET", VISITS), visit)["canReserve"]
        late = await _reserve(student, (await _quote(student, _category_of(listing)))["id"], visit)
        seen["too late"] = (late.json()["code"], late.json()["detail"])
        return seen

    seen = run(scenario)

    assert seen["someone else's"] == 404
    assert seen["another PG"] == ("VISIT_NOT_ON_SITE", "That visit was to another PG.")
    assert seen["next day"] is False
    assert seen["too late"] == (
        "VISIT_NOT_ON_SITE",
        "Reserving on the spot is for the day of the visit.",
    )
