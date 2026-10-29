"""Policies, caps and rent bands in the API (step 4.1, ADR 0036): the seeded defaults in force,
admins changing them (each a new version, audited, and the web app told), what the founders'
rules refuse, two changes at once, and rent bands.

The changes here are made long after the clock the other tests run at (NOW), so the versions in
force for them stay the seeded defaults."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.config import Settings
from app.core.actor import Role
from app.core.audit import AuditLog
from tests.jobs import RecordedWebCache, run_due_jobs
from tests.staff_api import NOW, Staff, run_as_staff, sign_in

pytestmark = pytest.mark.integration

LATER = NOW + timedelta(days=400)
BOOKING: dict[str, Any] = {
    "tokenPaise": 200_000,
    "holdMinutes": 15,
    "freeCancelDays": 7,
    "checkWindowHours": 24,
    "confirmDeadlineHours": 12,
    "noShowDays": 3,
    "lateCancelPolicy": "refund_full",
    "maxActiveHoldsPerUser": 1,
    "maxAdvanceDays": 120,
}
BAND: dict[str, Any] = {
    "locality": "kamla-nagar",
    "occupancy": "double",
    "minRentPaise": 800_000,
    "maxRentPaise": 1_400_000,
    "source": "internal",
}


@pytest.fixture
def run(make_settings: Callable[..., Settings], database_url: str) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Staff], Awaitable[Any]]) -> Any:
        return run_as_staff(make_settings(database_url=database_url), scenario, role=Role.ADMIN)

    return run_scenario


async def _admin_at(staff: Staff, moment: Any) -> Staff:
    """An admin signed in at ``moment``: a staff session doesn't outlast a jump of the clock."""
    staff.app.state.clock.set(moment)
    return await sign_in(staff.app, staff.client, Role.ADMIN)


async def _audited(staff: Staff, entity_type: str) -> list[dict[str, Any]]:
    async with staff.app.state.sessionmaker() as db:
        rows = await db.scalars(
            select(AuditLog).where(AuditLog.entity_type == entity_type).order_by(AuditLog.id)
        )
        return [{"action": row.action, "details": row.details} for row in rows]


def test_the_defaults_are_in_force_and_admins_change_them_from_then_on(
    run: Callable[..., Any],
) -> None:
    async def scenario(admin: Staff) -> dict[str, Any]:
        seen: dict[str, Any] = {"public": await admin.ok("GET", "/v1/policies")}
        seen["admin"] = await admin.ok("GET", "/v1/admin/policies")
        admin = await _admin_at(admin, LATER)
        web = RecordedWebCache()
        seen["changed"] = await admin.ok(
            "POST",
            "/v1/admin/policies/booking",
            json=BOOKING | {"tokenPaise": 150_000, "note": "A smaller token for the season."},
        )
        await run_due_jobs(admin.app, web_cache=web)
        seen["revalidated"] = web.tags
        seen["public after"] = await admin.ok("GET", "/v1/policies")
        seen["again"] = (
            await admin.call(
                "POST", "/v1/admin/policies/booking", json=BOOKING | {"tokenPaise": 150_000}
            )
        ).json()
        seen["refused"] = (
            await admin.call(
                "POST",
                "/v1/admin/policies/booking",
                json=BOOKING | {"tokenPaise": 250_000, "lateCancelPolicy": "split"},
            )
        ).json()
        seen["caps refused"] = (
            await admin.call(
                "POST",
                "/v1/admin/policies/caps",
                json={"maxPremiumBps": 4000, "maxDiscountBps": 9500, "roundingStepPaise": 5050},
            )
        ).json()
        # Two admins at once: one change goes, the other is told to reload.
        admin = await _admin_at(admin, LATER + timedelta(minutes=5))
        other = await sign_in(admin.app, admin.client, Role.ADMIN)
        answers = await asyncio.gather(
            admin.call(
                "POST",
                "/v1/admin/policies/fee",
                json={"rateBps": 2500, "gstRateBps": 1800, "gstMode": "exclusive"},
            ),
            other.call(
                "POST",
                "/v1/admin/policies/fee",
                json={"rateBps": 2800, "gstRateBps": 1800, "gstMode": "exclusive"},
            ),
        )
        seen["at once"] = sorted(answer.status_code for answer in answers)
        seen["history"] = await admin.ok("GET", "/v1/admin/policies/history")
        seen["audit"] = await _audited(admin, "booking_policy")
        return seen

    seen = run(scenario)

    # PRODUCT_CONTEXT §9's defaults, seeded (rules 2, 3, 8 and 9).
    assert seen["public"] == {
        "placementFee": {
            "rateBps": 3000,
            "basis": "listed_rent",
            "gstRateBps": 1800,
            "gstMode": "exclusive",
        },
        "booking": {
            "tokenPaise": 200000,
            "holdMinutes": 15,
            "freeCancelDays": 7,
            "checkWindowHours": 24,
            "confirmDeadlineHours": 12,
            "lateCancelPolicy": "refund_full",
        },
    }
    seeded = seen["admin"]
    assert seeded["caps"] | {"id": None, "effectiveFrom": None} == {
        "id": None,
        "effectiveFrom": None,
        "effectiveTo": None,
        "changedBy": None,
        "note": "The defaults in PRODUCT_CONTEXT §9.",
        "maxPremiumBps": 4000,
        "maxDiscountBps": 3000,
        "roundingStepPaise": 5000,
    }
    changed = seen["changed"]
    assert (changed["tokenPaise"], changed["note"]) == (150000, "A smaller token for the season.")
    assert changed["effectiveFrom"].startswith(LATER.date().isoformat())
    assert changed["changedBy"] is not None
    assert seen["revalidated"] == [["policies"]]
    assert seen["public after"]["booking"]["tokenPaise"] == 150000
    assert seen["again"]["code"] == "POLICY_INVALID"
    refused = seen["refused"]
    assert refused["code"] == "POLICY_INVALID"
    assert "the token must be from ₹1,000 to ₹2,000" in refused["detail"]
    assert "only refund_full works" in refused["detail"]
    assert "the discount cap must be from 0 to 90%" in seen["caps refused"]["detail"]
    assert "whole rupees" in seen["caps refused"]["detail"]
    assert seen["at once"] == [200, 409]
    history = seen["history"]
    # Newest first, each ending where the next began.
    booking = history["booking"]
    assert [version["tokenPaise"] for version in booking] == [150000, 200000]
    assert booking[1]["effectiveTo"] == booking[0]["effectiveFrom"]
    assert len(history["fee"]) == 2
    assert history["fee"][0]["effectiveTo"] is None
    [entry] = seen["audit"]
    assert entry["action"] == "pricing.booking_policy_changed"
    assert entry["details"]["before"]["token_paise"] == 200000
    assert entry["details"]["after"]["token_paise"] == 150000


def test_a_locality_has_one_band_in_force_for_each_occupancy(run: Callable[..., Any]) -> None:
    async def scenario(admin: Staff) -> dict[str, Any]:
        admin = await _admin_at(admin, LATER)
        seen: dict[str, Any] = {"first": await admin.ok("POST", "/v1/admin/rent-bands", json=BAND)}
        admin = await _admin_at(admin, LATER + timedelta(days=1))
        seen["second"] = await admin.ok(
            "POST",
            "/v1/admin/rent-bands",
            json=BAND | {"minRentPaise": 900_000, "maxRentPaise": 1_500_000},
        )
        seen["in force"] = await admin.ok(
            "GET", "/v1/admin/rent-bands", params={"locality": "kamla-nagar"}
        )
        seen["with ended"] = await admin.ok(
            "GET", "/v1/admin/rent-bands", params={"locality": "kamla-nagar", "ended": "true"}
        )
        seen["no reference"] = (
            await admin.call("POST", "/v1/admin/rent-bands", json=BAND | {"source": "official"})
        ).json()
        seen["upside down"] = (
            await admin.call(
                "POST",
                "/v1/admin/rent-bands",
                json=BAND | {"minRentPaise": 1_600_000, "locality": "nowhere-at-all"},
            )
        ).json()
        admin = await _admin_at(admin, LATER + timedelta(days=2))
        seen["ended"] = await admin.ok(
            "POST", f"/v1/admin/rent-bands/{seen['second']['id']}/end", json={"note": "Too low."}
        )
        seen["ended again"] = (
            await admin.call("POST", f"/v1/admin/rent-bands/{seen['second']['id']}/end", json={})
        ).json()
        seen["none"] = await admin.ok(
            "GET", "/v1/admin/rent-bands", params={"locality": "kamla-nagar"}
        )
        seen["audit"] = [entry["action"] for entry in await _audited(admin, "rent_band")]
        return seen

    seen = run(scenario)

    first, second = seen["first"], seen["second"]
    assert first["locality"] == {"slug": "kamla-nagar", "name": "Kamla Nagar"}
    assert (second["minRentPaise"], second["maxRentPaise"]) == (900000, 1500000)
    assert [band["id"] for band in seen["in force"]["items"]] == [second["id"]]
    ended = {band["id"]: band for band in seen["with ended"]["items"]}
    assert ended[first["id"]]["effectiveTo"] == second["effectiveFrom"]
    assert "an official band needs its reference" in seen["no reference"]["detail"]
    upside_down = seen["upside down"]["detail"]
    assert "no locality has that slug" in upside_down
    assert "the lowest rent must be above zero and no more than the highest" in upside_down
    assert seen["ended"]["note"] == second["note"]
    assert seen["ended"]["effectiveTo"] is not None
    assert seen["ended again"]["code"] == "INVALID_TRANSITION"
    assert seen["none"]["items"] == []
    assert seen["audit"] == [
        "pricing.rent_band_set",
        "pricing.rent_band_set",
        "pricing.rent_band_ended",
    ]
