"""Owners and the owner agreement (step 2.6, ADR 0025): ops add and edit owners; owners, signed in
by phone, accept the current agreement as they were shown it, and ops see every acceptance."""

import hashlib
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.config import BRAND_NAME, Settings
from app.core.actor import Role
from app.core.audit import AuditLog
from app.jobs import EXPORTERS
from app.modules.catalog.domain.agreements import Agreement
from app.modules.catalog.service import owner_data
from app.modules.identity.domain.sessions import SessionKind
from app.modules.identity.repository import UserRepository
from app.modules.identity.service import SessionService
from tests.agreements import FixedAgreements
from tests.staff_api import NOW, Staff, as_owner, phone, run_as_staff

pytestmark = pytest.mark.integration

Ops = Staff
BROWSER = "Mozilla/5.0 (Linux; Android 14) a fictional phone browser"


@pytest.fixture
def run(make_settings: Callable[..., Settings], database_url: str) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Ops], Awaitable[Any]], *, role: Role = Role.OPS) -> Any:
        return run_as_staff(make_settings(database_url=database_url), scenario, role=role)

    return run_scenario


async def _audited(ops: Ops, action: str, entity_id: str) -> list[dict[str, Any]]:
    async with ops.app.state.sessionmaker() as db:
        rows = await db.scalars(
            select(AuditLog).where(AuditLog.action == action, AuditLog.entity_id == entity_id)
        )
        return [{"actor": row.actor_type, "details": row.details} for row in rows]


async def _exported(ops: Ops, person: Staff) -> dict[str, Any]:
    """The catalog's part of ``person``'s data export, as the export job builds it."""
    assert owner_data in EXPORTERS
    async with ops.app.state.sessionmaker() as db, db.begin():
        return await owner_data(db, person.user_id)


def test_an_owner_accepts_the_agreement_they_were_shown_and_ops_see_when_and_from_where(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Ops) -> dict[str, Any]:
        added = await ops.owner()
        owner = await as_owner(ops, added)
        before = await owner.ok("GET", "/v1/owner/profile")
        agreement = await owner.ok("GET", "/v1/owner/agreement")
        accepted = await owner.ok(
            "POST",
            "/v1/owner/agreement/acceptances",
            json={"version": agreement["version"], "documentSha256": agreement["documentSha256"]},
            headers={"User-Agent": BROWSER},
        )
        again = await owner.ok(
            "POST",
            "/v1/owner/agreement/acceptances",
            json={"version": agreement["version"], "documentSha256": agreement["documentSha256"]},
        )
        return {
            "added": added,
            "before": before,
            "agreement": agreement,
            "accepted": accepted,
            "again": again,
            "now": await owner.ok("GET", "/v1/owner/agreement"),
            "profile": await owner.ok("GET", "/v1/owner/profile"),
            "ops see": await ops.ok("GET", f"/v1/ops/owners/{added['id']}"),
            "history": await ops.ok("GET", f"/v1/ops/owners/{added['id']}/agreements"),
            "audit": await _audited(ops, "catalog.owner_agreement_accepted", added["id"]),
            "export": await _exported(ops, owner),
        }

    found = run(scenario)

    added, agreement, accepted = found["added"], found["agreement"], found["accepted"]
    assert (added["agreementVersion"], added["agreementCurrent"]) == (None, False)
    assert found["before"] == added
    # The draft, with the brand filled in, and the hash of exactly that text.
    assert agreement["version"] == "draft-2"
    assert agreement["text"].startswith(f"# {BRAND_NAME} owner agreement")
    assert "DRAFT" in agreement["text"]
    assert agreement["documentSha256"] == hashlib.sha256(agreement["text"].encode()).hexdigest()
    assert (agreement["accepted"], agreement["acceptedAt"], agreement["acceptedVersion"]) == (
        False,
        None,
        None,
    )
    assert accepted == {
        "version": "draft-2",
        "documentSha256": agreement["documentSha256"],
        "acceptedAt": NOW.isoformat().replace("+00:00", "Z"),
        "ip": "127.0.0.1",
        "userAgent": BROWSER,
    }
    # Accepting again records nothing new.
    assert found["again"] == accepted
    assert found["history"]["items"] == [accepted]
    now = found["now"]
    assert (now["accepted"], now["acceptedAt"], now["acceptedVersion"]) == (
        True,
        accepted["acceptedAt"],
        "draft-2",
    )
    for seen in (found["profile"], found["ops see"]):
        assert (seen["agreementVersion"], seen["agreementCurrent"]) == ("draft-2", True)
    assert found["audit"] == [
        {
            "actor": "owner",
            "details": {"version": "draft-2", "document_sha256": agreement["documentSha256"]},
        }
    ]
    # The owner's data export holds the business and the acceptance, IP and browser included.
    exported = found["export"]["owner"]
    assert (exported["id"], exported["agreementVersion"]) == (added["id"], "draft-2")
    assert exported["agreementAcceptances"] == [
        {
            "version": "draft-2",
            "documentSha256": agreement["documentSha256"],
            "acceptedAt": NOW.isoformat(),
            "ipAddress": "127.0.0.1",
            "userAgent": BROWSER,
        }
    ]


def test_an_agreement_that_changed_is_refused_and_a_new_version_asks_owners_again(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Ops) -> dict[str, Any]:
        added = await ops.owner()
        owner = await as_owner(ops, added)
        first = await owner.ok("GET", "/v1/owner/agreement")
        stale = {"version": first["version"], "documentSha256": "0" * 64}
        refused = [
            await owner.call("POST", "/v1/owner/agreement/acceptances", json=body)
            for body in (stale, {"version": "draft-0", "documentSha256": first["documentSha256"]})
        ]
        await owner.ok(
            "POST",
            "/v1/owner/agreement/acceptances",
            json={"version": first["version"], "documentSha256": first["documentSha256"]},
        )
        # A new version is published: what a deploy with OWNER_AGREEMENT_VERSION=draft-3 does.
        ops.app.state.agreements = FixedAgreements(
            Agreement("draft-2", first["text"]), Agreement("draft-3", "A fictional next draft.")
        )
        ops.app.state.owner_agreement_version = "draft-3"
        second = await owner.ok("GET", "/v1/owner/agreement")
        profile = await owner.ok("GET", "/v1/owner/profile")
        old = await owner.call(
            "POST",
            "/v1/owner/agreement/acceptances",
            json={"version": first["version"], "documentSha256": first["documentSha256"]},
        )
        await owner.ok(
            "POST",
            "/v1/owner/agreement/acceptances",
            json={"version": second["version"], "documentSha256": second["documentSha256"]},
        )
        history = await ops.ok("GET", f"/v1/ops/owners/{added['id']}/agreements")
        return {
            "refused": [(r.status_code, r.json()["code"]) for r in refused],
            "second": second,
            "profile": profile,
            "old": (old.status_code, old.json()["code"]),
            "history": [item["version"] for item in history["items"]],
        }

    found = run(scenario)

    assert found["refused"] == [(409, "AGREEMENT_CHANGED")] * 2
    second = found["second"]
    assert (second["version"], second["text"]) == ("draft-3", "A fictional next draft.")
    assert (second["accepted"], second["acceptedAt"], second["acceptedVersion"]) == (
        False,
        None,
        "draft-2",
    )
    assert (found["profile"]["agreementVersion"], found["profile"]["agreementCurrent"]) == (
        "draft-2",
        False,
    )
    # The version the owner accepted before can't be accepted now it isn't current.
    assert found["old"] == (409, "AGREEMENT_CHANGED")
    assert found["history"] == ["draft-3", "draft-2"]


def test_ops_change_an_owners_business_details(run: Callable[..., Any]) -> None:
    async def scenario(ops: Ops) -> dict[str, Any]:
        added = await ops.owner()
        path = f"/v1/ops/owners/{added['id']}"
        changed = await ops.ok(
            "PATCH",
            path,
            json={
                "legalName": "  Fictional Homes LLP ",
                "businessName": "Fictional Homes",
                "gstin": "07aaacf1234a1zh",
            },
        )
        untouched = await ops.ok("PATCH", path, json={"businessName": "Fictional Homes Two"})
        # The same value again changes nothing, so it isn't audited.
        await ops.ok("PATCH", path, json={"businessName": "Fictional Homes Two "})
        cleared = await ops.ok("PATCH", path, json={"gstin": None})
        refused = [
            await ops.call("PATCH", path, json=body)
            for body in ({"gstin": "not a gstin"}, {"legalName": " "}, {"phone": "9999999999"})
        ]
        return {
            "added": added,
            "changed": changed,
            "untouched": untouched,
            "cleared": cleared,
            "read": await ops.ok("GET", path),
            "refused": [(r.status_code, r.json().get("code")) for r in refused],
            "missing": (
                await ops.call("GET", "/v1/ops/owners/0190f0e0-0000-7000-8000-000000000000")
            ).status_code,
            "audit": await _audited(ops, "catalog.owner_updated", added["id"]),
        }

    found = run(scenario)

    changed = found["changed"]
    assert (changed["legalName"], changed["businessName"]) == (
        "Fictional Homes LLP",
        "Fictional Homes",
    )
    assert changed["gstin"] == "07AAACF1234A1ZH"
    # Only what's sent changes.
    assert found["untouched"]["legalName"] == "Fictional Homes LLP"
    assert found["untouched"]["gstin"] == "07AAACF1234A1ZH"
    assert found["cleared"]["gstin"] is None
    assert found["read"] == found["cleared"]
    assert found["read"]["phone"] == found["added"]["phone"]
    assert found["refused"] == [
        (422, "LISTING_INVALID"),
        (422, "LISTING_INVALID"),
        (422, "VALIDATION_ERROR"),
    ]
    assert found["missing"] == 404
    assert [entry["details"]["fields"] for entry in found["audit"]] == [
        ["business_name", "gstin", "legal_name"],
        ["business_name"],
        ["gstin"],
    ]


def test_only_an_owner_with_a_business_record_has_an_owner_area(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Ops) -> dict[str, list[int]]:
        app = ops.app
        async with app.state.sessionmaker() as db, db.begin():
            student = await UserRepository(db).add(
                phone_e164=f"+91{phone()}", roles=(Role.STUDENT,)
            )
            waiting = await UserRepository(db).add(phone_e164=f"+91{phone()}", roles=(Role.OWNER,))
        callers: dict[str, Staff] = {"ops": ops}
        for name, user in (("student", student), ("owner without a record", waiting)):
            async with app.state.sessionmaker() as db:
                session = await SessionService(db, app.state.clock).start(
                    user.id, kind=SessionKind.USER, ip_address=None, user_agent=None
                )
            callers[name] = Staff(app, ops.client, user_id=user.id, token=session.token)
        agreement = app.state.agreements.get(app.state.owner_agreement_version)
        body = {"version": agreement.version, "documentSha256": agreement.sha256}
        statuses: dict[str, list[int]] = {}
        for name, caller in callers.items():
            statuses[name] = [
                (await caller.call("GET", "/v1/owner/profile")).status_code,
                (await caller.call("GET", "/v1/owner/agreement")).status_code,
                (
                    await caller.call("POST", "/v1/owner/agreement/acceptances", json=body)
                ).status_code,
            ]
        return statuses

    assert run(scenario) == {
        "ops": [403, 403, 403],
        "student": [403, 403, 403],
        "owner without a record": [404, 404, 404],
    }


def test_the_database_refuses_to_change_or_remove_an_acceptance(run: Callable[..., Any]) -> None:
    async def scenario(ops: Ops) -> list[str]:
        added = await ops.owner()
        owner = await as_owner(ops, added)
        agreement = await owner.ok("GET", "/v1/owner/agreement")
        await owner.ok(
            "POST",
            "/v1/owner/agreement/acceptances",
            json={"version": agreement["version"], "documentSha256": agreement["documentSha256"]},
        )
        errors = []
        for statement in (
            "UPDATE owner_agreements SET accepted_ip = '10.0.0.1'",
            "DELETE FROM owner_agreements",
            "TRUNCATE owner_agreements CASCADE",
        ):
            async with ops.app.state.sessionmaker() as db:
                with pytest.raises(DBAPIError) as refused:
                    async with db.begin():
                        await db.execute(text(statement))
                errors.append(str(refused.value))
        return errors

    errors = run(scenario)

    assert len(errors) == 3
    assert all("owner_agreements is append-only" in error for error in errors)
