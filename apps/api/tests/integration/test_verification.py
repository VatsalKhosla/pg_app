"""Field verification end to end (step 2.5): ops book a visit for a field agent, the agent reports
from the building, and the listing is verified, failed or suspended. Done when a property moves
unverified → scheduled → verified with a stored report and photos.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import event

from app.config import Settings
from app.core.actor import Role
from app.modules.media.domain.assets import AssetStatus, Purpose
from tests.staff_api import (
    CHECKLIST,
    NOW,
    Staff,
    book,
    report,
    run_as_staff,
    sign_in,
    spot,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def run(make_settings: Callable[..., Settings], database_url: str) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Staff], Awaitable[Any]]) -> Any:
        return run_as_staff(make_settings(database_url=database_url), scenario)

    return run_scenario


async def _sellable(ops: Staff, *, at: dict[str, float]) -> dict[str, Any]:
    """A listing with a single room and its bed: something to sell once verified."""
    listing = await ops.listing(await ops.owner(), at=at)
    built = await ops.ok(
        "POST",
        f"/v1/ops/properties/{listing['id']}/room-categories",
        json={
            "occupancy": "single",
            "label": "Single",
            "baseRentPaise": 1_400_000,
            "securityDepositPaise": 1_400_000,
        },
    )
    category = built["categories"][0]["id"]
    return await ops.ok(
        "POST", f"/v1/ops/room-categories/{category}/rooms", json={"label": "1", "beds": 1}
    )


async def _publish(ops: Staff, listing_id: str) -> dict[str, Any]:
    return await ops.ok(
        "POST", f"/v1/ops/properties/{listing_id}/status", json={"status": "published"}
    )


def test_a_visit_verifies_a_listing_with_its_report_and_photos(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        agent = await sign_in(ops.app, ops.client, Role.FIELD_AGENT)
        listing = await _sellable(ops, at=spot(1_200))
        visit = await book(ops, agent, listing["id"])
        steps: dict[str, Any] = {
            "visit": visit,
            "booked": await ops.ok("GET", f"/v1/ops/properties/{listing['id']}"),
            "agents": await ops.ok("GET", "/v1/ops/field-agents"),
            "mine": await agent.ok("GET", "/v1/ops/verification-visits"),
            "seen": await agent.ok("GET", f"/v1/ops/verification-visits/{visit['id']}"),
        }
        # The agent stands about 40 m from the pin.
        reported = await report(agent, visit, at=spot(1_240))
        steps |= {
            "reported": reported.json(),
            "verified": await ops.ok("GET", f"/v1/ops/properties/{listing['id']}"),
            "published": await _publish(ops, listing["id"]),
            "visits": await ops.ok(
                "GET", f"/v1/ops/properties/{listing['id']}/verification-visits"
            ),
            "history": await ops.ok("GET", f"/v1/ops/properties/{listing['id']}/history"),
            "agent_id": str(agent.user_id),
        }
        assert reported.status_code == 200, reported.text
        return steps

    steps = run(scenario)

    visit = steps["visit"]
    assert visit["status"] == "scheduled"
    assert visit["scheduledFor"] == NOW.isoformat().replace("+00:00", "Z")
    assert steps["booked"]["verificationStatus"] == "scheduled"
    assert (steps["booked"]["canBookVisit"], steps["booked"]["canSuspend"]) == (False, False)
    assert (steps["verified"]["canBookVisit"], steps["verified"]["canSuspend"]) == (False, True)
    assert visit["agent"]["id"] in {agent["id"] for agent in steps["agents"]["items"]}
    # The agent sees the visit booked for them, with what they need to find the building.
    assert [item["id"] for item in steps["mine"]["items"]] == [visit["id"]]
    seen = steps["seen"]["property"]
    assert seen["addressLine"] == "House 1, a fictional lane"
    assert seen["location"] == spot(1_200)
    assert seen["ownerPhone"].startswith("+91")
    done = steps["reported"]
    assert done["status"] == "submitted"
    assert done["result"] == "passed"
    assert done["submittedAt"] == NOW.isoformat().replace("+00:00", "Z")
    assert done["position"] == spot(1_240)
    assert 35 <= done["distanceM"] <= 45
    assert done["accuracyM"] == 8
    assert done["checklist"] == CHECKLIST
    # Report photos are private: their links are signed.
    [photo] = done["photos"]
    assert "Signature" in photo["renditions"][0]["url"]
    assert steps["verified"]["verificationStatus"] == "verified"
    assert steps["verified"]["problems"] == []
    assert steps["published"]["status"] == "published"
    assert [item["status"] for item in steps["visits"]["items"]] == ["submitted"]
    actions = {entry["action"] for entry in steps["history"]["items"]}
    assert {"catalog.verification_scheduled", "catalog.verification_submitted"} <= actions


def test_a_failed_visit_needs_its_reasons_and_a_flagged_building_cant_pass(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        agent = await sign_in(ops.app, ops.client, Role.FIELD_AGENT)
        listing = await _sellable(ops, at=spot(1_400))
        visit = await book(ops, agent, listing["id"])
        at = listing["location"]
        flagged = CHECKLIST | {"authorityNotice": True}
        steps = {
            "flagged": await report(agent, visit, at=at, checklist=flagged),
            "no notes": await report(agent, visit, at=at, result="failed"),
            "outside": await report(agent, visit, at={"lat": 19.07, "lng": 72.87}),
            "no photos": await report(agent, visit, at=at, photos=[]),
            "failed": await report(
                agent, visit, at=at, checklist=flagged, result="failed", notes="Sealed by MCD"
            ),
            "again": await report(agent, visit, at=at),
        }
        steps["after"] = await ops.call("GET", f"/v1/ops/properties/{listing['id']}")
        steps["publish"] = await ops.call(
            "POST", f"/v1/ops/properties/{listing['id']}/status", json={"status": "published"}
        )
        return {name: (response.status_code, response.json()) for name, response in steps.items()}

    steps = run(scenario)

    assert steps["flagged"][0] == 422
    assert "notice from the authorities" in steps["flagged"][1]["detail"]
    assert steps["no notes"][0] == 422
    assert "needs notes" in steps["no notes"][1]["detail"]
    assert steps["outside"][0] == 422
    assert steps["no photos"][0] == 422
    assert steps["failed"] == (200, steps["failed"][1])
    assert steps["failed"][1]["result"] == "failed"
    assert steps["failed"][1]["notes"] == "Sealed by MCD"
    assert steps["again"][0] == 409
    assert steps["after"][1]["verificationStatus"] == "rejected"
    assert steps["publish"][0] == 409
    assert steps["publish"][1]["detail"] == "failed its verification visit"


def test_only_the_agent_it_was_booked_for_sees_or_reports_on_a_visit(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, int]:
        agent = await sign_in(ops.app, ops.client, Role.FIELD_AGENT)
        other = await sign_in(ops.app, ops.client, Role.FIELD_AGENT)
        listing = await _sellable(ops, at=spot(1_600))
        visit = await book(ops, agent, listing["id"])
        path = f"/v1/ops/verification-visits/{visit['id']}"
        mine = await other.ok("GET", "/v1/ops/verification-visits")
        return {
            "other reads": (await other.call("GET", path)).status_code,
            "other reports": (await report(other, visit, at=listing["location"])).status_code,
            "other lists": len([item for item in mine["items"] if item["id"] == visit["id"]]),
            "agent books": (
                await agent.call(
                    "POST",
                    f"/v1/ops/properties/{listing['id']}/verification-visits",
                    json={"agent": visit["agent"]["id"], "scheduledFor": NOW.isoformat()},
                )
            ).status_code,
            "agent cancels": (
                await agent.call("POST", f"{path}/cancel", json={"reason": "Not me"})
            ).status_code,
            "agent lists all properties": (
                await agent.call("GET", f"/v1/ops/properties/{listing['id']}/verification-visits")
            ).status_code,
            "ops reports": (await report(ops, visit, at=listing["location"])).status_code,
            "ops reads": (await ops.call("GET", path)).status_code,
        }

    outcome = run(scenario)

    assert outcome == {
        "other reads": 404,
        "other reports": 404,
        "other lists": 0,
        "agent books": 403,
        "agent cancels": 403,
        "agent lists all properties": 403,
        "ops reports": 403,
        "ops reads": 200,
    }


def test_a_cancelled_visit_puts_the_status_back_and_one_visit_is_booked_at_a_time(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        agent = await sign_in(ops.app, ops.client, Role.FIELD_AGENT)
        listing = await _sellable(ops, at=spot(1_800))
        visit = await book(ops, agent, listing["id"])
        path = f"/v1/ops/verification-visits/{visit['id']}"
        twice = await ops.call(
            "POST",
            f"/v1/ops/properties/{listing['id']}/verification-visits",
            json={"agent": visit["agent"]["id"], "scheduledFor": NOW.isoformat()},
        )
        cancelled = await ops.ok("POST", f"{path}/cancel", json={"reason": "The owner moved it"})
        return {
            "twice": twice.status_code,
            "cancelled": cancelled,
            "again": (
                await ops.call("POST", f"{path}/cancel", json={"reason": "Again"})
            ).status_code,
            "report": (await report(agent, visit, at=listing["location"])).status_code,
            "after": await ops.ok("GET", f"/v1/ops/properties/{listing['id']}"),
            "rebooked": await book(ops, agent, listing["id"]),
        }

    steps = run(scenario)

    assert steps["twice"] == 409
    assert steps["cancelled"]["status"] == "cancelled"
    assert steps["cancelled"]["cancelReason"] == "The owner moved it"
    assert steps["again"] == 409
    assert steps["report"] == 409
    assert steps["after"]["verificationStatus"] == "unverified"
    assert steps["rebooked"]["status"] == "scheduled"


def test_a_suspended_listing_comes_down_until_a_new_visit_passes(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        agent = await sign_in(ops.app, ops.client, Role.FIELD_AGENT)
        listing = await _sellable(ops, at=spot(2_000))
        first = await book(ops, agent, listing["id"])
        await report(agent, first, at=listing["location"])
        await _publish(ops, listing["id"])
        suspend = f"/v1/ops/properties/{listing['id']}/verification/suspend"
        steps: dict[str, Any] = {
            "suspended": await ops.ok("POST", suspend, json={"reason": "A fire safety complaint"}),
            "twice": (await ops.call("POST", suspend, json={"reason": "Again"})).status_code,
            "publish": (
                await ops.call(
                    "POST",
                    f"/v1/ops/properties/{listing['id']}/status",
                    json={"status": "published"},
                )
            ).status_code,
        }
        second = await book(ops, agent, listing["id"])
        await report(agent, second, at=listing["location"])
        steps["republished"] = await _publish(ops, listing["id"])
        history = await ops.ok("GET", f"/v1/ops/properties/{listing['id']}/history")
        steps["history"] = [
            (entry["action"], entry["details"].get("reason"))
            for entry in history["items"]
            if entry["action"]
            in {"catalog.verification_suspended", "catalog.property_status_changed"}
        ]
        return steps

    steps = run(scenario)

    suspended = steps["suspended"]
    assert (suspended["verificationStatus"], suspended["status"]) == ("suspended", "paused")
    assert steps["twice"] == 409
    assert steps["publish"] == 409
    assert steps["republished"]["status"] == "published"
    assert ("catalog.verification_suspended", "A fire safety complaint") in steps["history"]
    assert ("catalog.property_status_changed", "verification suspended") in steps["history"]


def test_the_agents_position_can_become_the_pin(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> tuple[dict[str, Any], dict[str, Any]]:
        agent = await sign_in(ops.app, ops.client, Role.FIELD_AGENT)
        listing = await _sellable(ops, at=spot(2_200))
        visit = await book(ops, agent, listing["id"])
        await report(agent, visit, at=spot(2_260), move_pin=True)
        return listing, await ops.ok("GET", f"/v1/ops/properties/{listing['id']}")

    before, after = run(scenario)

    assert after["location"] == spot(2_260)
    assert after["displayLocation"] != before["displayLocation"]


def test_a_report_takes_only_the_agents_own_ready_verification_photos(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> list[str]:
        agent = await sign_in(ops.app, ops.client, Role.FIELD_AGENT)
        other = await sign_in(ops.app, ops.client, Role.FIELD_AGENT)
        listing = await _sellable(ops, at=spot(2_400))
        visit = await book(ops, agent, listing["id"])
        at = listing["location"]
        photos = [
            await agent.media(),
            await other.media(purpose=Purpose.VERIFICATION_PHOTO),
            await agent.media(AssetStatus.PROCESSING, purpose=Purpose.VERIFICATION_PHOTO),
        ]
        details = []
        for photo in photos:
            response = await report(agent, visit, at=at, photos=[photo])
            assert response.status_code == 422, response.text
            details.append(response.json()["detail"])
        return details

    not_verification, not_theirs, not_ready = run(scenario)

    assert "isn't a verification photo" in not_verification
    assert "no such photo" in not_theirs
    assert "is processing" in not_ready


def test_a_visit_needs_a_field_agent_and_a_time_that_makes_sense(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> list[int]:
        agent = await sign_in(ops.app, ops.client, Role.FIELD_AGENT)
        listing = await _sellable(ops, at=spot(2_600))
        path = f"/v1/ops/properties/{listing['id']}/verification-visits"
        agent_id = await agent.public_id()
        return [
            (await ops.call("POST", path, json=body)).status_code
            for body in (
                # Staff, but not a field agent; and nobody at all.
                {"agent": await ops.public_id(), "scheduledFor": NOW.isoformat()},
                {"agent": str(uuid.uuid4()), "scheduledFor": NOW.isoformat()},
                {"agent": agent_id, "scheduledFor": (NOW + timedelta(days=61)).isoformat()},
                {"agent": agent_id, "scheduledFor": (NOW - timedelta(hours=2)).isoformat()},
                # No time zone: refused rather than guessed.
                {"agent": agent_id, "scheduledFor": "2027-07-14T10:00:00"},
            )
        ]

    assert run(scenario) == [422, 422, 422, 422, 422]


def test_visits_read_in_the_same_number_of_queries_however_many(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> tuple[int, int]:
        agent = await sign_in(ops.app, ops.client, Role.FIELD_AGENT)
        statements = 0

        def count(*_: object) -> None:
            nonlocal statements
            statements += 1

        async def read() -> int:
            nonlocal statements
            statements = 0
            event.listen(ops.app.state.engine.sync_engine, "before_cursor_execute", count)
            try:
                await agent.ok("GET", "/v1/ops/verification-visits")
            finally:
                event.remove(ops.app.state.engine.sync_engine, "before_cursor_execute", count)
            return statements

        first = await _sellable(ops, at=spot(3_000))
        await report(agent, await book(ops, agent, first["id"]), at=first["location"])
        few = await read()
        for metres in (3_200, 3_400, 3_600):
            listing = await _sellable(ops, at=spot(metres))
            await report(agent, await book(ops, agent, listing["id"]), at=listing["location"])
        return few, await read()

    few, many = run(scenario)

    assert few == many
