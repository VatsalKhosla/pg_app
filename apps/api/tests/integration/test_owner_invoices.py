"""Owners' invoices (step 6.5, ADR 0061). Done when the ₹10,000 example produces an invoice of
₹3,540 with ₹2,000 applied and ₹1,540 due: issued as the booking settles, numbered without gaps, its
PDF private, and its balance paid through a payment link that only the gateway's word marks paid."""

import asyncio
import re
import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.config import Settings
from app.core.outbox import enqueue
from app.modules.booking.jobs import CHECK_WINDOWS
from app.modules.identity.domain.sessions import SessionKind
from app.modules.invoices.models import OwnerInvoice
from app.modules.invoices.repository import InvoiceRepository
from app.modules.payments.domain.links import GatewayLink, LinkStatus
from app.modules.payments.domain.payments import PaymentPurpose
from app.modules.payments.models import Payment
from tests.flags import FixedFlags
from tests.integration.test_booking_check_in import MOVED_IN
from tests.integration.test_booking_confirmation import _owner_of
from tests.integration.test_booking_holds import _listing
from tests.integration.test_booking_student import _again
from tests.integration.test_ledger import REASON, _balances
from tests.integration.test_payment_refunds import _ask, _paid
from tests.integration.test_payment_webhooks import _send
from tests.integration.test_payments_checkout import _gateway
from tests.jobs import RecordedTexts, run_due_jobs
from tests.staff_api import Staff, as_owner, run_as_staff
from tests.storage import BUCKETS, MemoryStorage

pytestmark = pytest.mark.integration

MINE = "/v1/owner/invoices"
NUMBER = re.compile(r"^FY[0-9]{4}-[0-9]{2}/[0-9]{6}$")


@pytest.fixture
def run(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Staff], Any]) -> Any:
        settings = make_settings(database_url=database_url, redis_url=valkey_url)

        async def remote_booking(ops: Staff) -> Any:
            ops.app.state.flags = FixedFlags(remote_booking_enabled=True)
            await run_due_jobs(ops.app)  # what other tests left waiting
            return await scenario(ops)

        return run_as_staff(settings, remote_booking)

    return run_scenario


async def _settled(
    ops: Staff, *, texts: RecordedTexts | None = None, storage: MemoryStorage | None = None
) -> tuple[Staff, Staff, str, dict[str, Any]]:
    """A ₹10,000 room's booking from its token to living there, and its listing's owner."""
    listing = await _listing(ops, beds=1)
    student, code, _ = await _paid(ops, listing)
    await ops.ok("POST", f"/v1/ops/bookings/{code}/confirm", json=REASON)
    ops.app.state.clock.set(MOVED_IN)
    student = await _again(student)
    await student.ok("POST", f"/v1/bookings/{code}/check-in")
    ops.app.state.clock.advance(timedelta(hours=24))
    async with ops.app.state.sessionmaker() as db, db.begin():
        await enqueue(db, CHECK_WINDOWS, {}, clock=ops.app.state.clock)
    await run_due_jobs(ops.app, texts=texts, storage=storage)
    ops = await _again(ops, kind=SessionKind.STAFF)
    return ops, await _owner_of(ops, listing), code, listing


async def _link_of(ops: Staff, invoice_id: str) -> Payment:
    async with ops.app.state.sessionmaker() as db:
        found: Payment | None = await db.scalar(
            select(Payment)
            .join(OwnerInvoice, OwnerInvoice.id == Payment.invoice_id)
            .where(OwnerInvoice.public_id == uuid.UUID(invoice_id))
            .order_by(Payment.id.desc())
            .limit(1)
        )
        assert found is not None
        return found


def test_the_ten_thousand_rupee_booking_is_invoiced_and_its_balance_paid_by_link(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        texts, storage = RecordedTexts(), MemoryStorage()
        ops, owner, code, _ = await _settled(ops, texts=texts, storage=storage)
        invoice = (await owner.ok("GET", MINE))["items"][0]
        stranger = await as_owner(ops, (await _listing(ops, beds=1))["owner"])
        file = await owner.call("GET", f"{MINE}/{invoice['id']}/file")
        stored = storage.objects[BUCKETS.private, f"invoices/{_year(invoice)}/{invoice['id']}.pdf"]
        seen: dict[str, Any] = {
            "invoice": invoice,
            "text": [
                (template, values)
                for _, template, values in texts.sent
                if template.startswith("owner_invoice") and values.get("code") == code
            ],
            "pdf": (
                stored[1],
                invoice["number"].encode() in stored[0],
                b"Draft invoice" in stored[0],
            ),
            "file": (
                file.status_code,
                file.headers["cache-control"],
                "invoices/" in file.headers["location"],
            ),
            "stranger": (await stranger.ok("GET", MINE))["items"],
            "stranger's file": (
                await stranger.call("GET", f"{MINE}/{invoice['id']}/file")
            ).status_code,
            "stranger pays": (
                await stranger.call("POST", f"{MINE}/{invoice['id']}/test-payment")
            ).status_code,
            "ops": (await ops.ok("GET", "/v1/ops/invoices", params={"booking": code}))["items"],
            "books before": await _balances(ops, code),
        }
        await owner.ok("POST", f"{MINE}/{invoice['id']}/test-payment")
        await run_due_jobs(ops.app)
        seen["after"] = (await owner.ok("GET", MINE))["items"][0]
        seen["books after"] = await _balances(ops, code)
        seen["paid again"] = (
            await owner.call("POST", f"{MINE}/{invoice['id']}/test-payment")
        ).json()["code"]
        return seen

    seen = run(scenario)

    invoice = seen["invoice"]
    assert NUMBER.match(invoice["number"])
    assert {
        key: invoice[key]
        for key in (
            "baseRentPaise",
            "feeRateBps",
            "gstRateBps",
            "gstIncluded",
            "feePaise",
            "gstPaise",
            "totalPaise",
            "tokenAppliedPaise",
            "tokenOverPaise",
            "balanceDuePaise",
            "status",
        )
    } == {
        "baseRentPaise": 1_000_000,
        "feeRateBps": 3_000,
        "gstRateBps": 1_800,
        "gstIncluded": False,
        "feePaise": 300_000,
        "gstPaise": 54_000,
        "totalPaise": 354_000,
        "tokenAppliedPaise": 200_000,
        "tokenOverPaise": 0,
        "balanceDuePaise": 154_000,
        "status": "issued",
    }
    assert invoice["pay"]["provider"] == "fake"
    assert invoice["hasFile"] is True
    assert seen["text"] == [
        (
            "owner_invoice_issued",
            {
                "brand": "Fix Your Stay",
                "number": invoice["number"],
                "code": invoice["booking"],
                "total": "₹3,540.00",
                "token": "₹2,000.00",
                "balance": "₹1,540.00",
            },
        )
    ]
    assert seen["pdf"] == ("application/pdf", True, True)
    assert seen["file"] == (303, "no-store", True)
    assert seen["stranger"] == []
    assert seen["stranger's file"] == 404
    assert seen["stranger pays"] == 404
    assert [(item["number"], item["owner"]) for item in seen["ops"]] == [
        (invoice["number"], seen["ops"][0]["owner"])
    ]
    # The owner owes ₹1,540 until they pay it, and then nothing; the books balance throughout.
    assert seen["books before"]["owner_receivable"] == 154_000
    assert seen["after"]["status"] == "paid"
    assert seen["after"]["paidAt"] is not None
    assert seen["after"]["pay"] is None
    assert seen["books after"] == {
        "gateway_clearing": 354_000,
        "placement_fee_revenue": -300_000,
        "gst_payable": -54_000,
    }
    assert seen["paid again"] == "INVALID_TRANSITION"


def _year(invoice: dict[str, Any]) -> str:
    return str(invoice["number"])[2:9]


def test_invoice_numbers_run_without_gaps_however_many_are_taken_at_once(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        year = f"t-{uuid.uuid4().hex[:8]}"  # a year of its own

        async def take() -> int:
            async with ops.app.state.sessionmaker() as db, db.begin():
                return await InvoiceRepository(db).next_serial(year)

        taken = await asyncio.gather(*(take() for _ in range(12)))
        async with ops.app.state.sessionmaker() as db:
            await db.begin()
            undone = await InvoiceRepository(db).next_serial(year)
            await db.rollback()
        return {"taken": sorted(taken), "undone": undone, "next": await take()}

    seen = run(scenario)

    assert seen["taken"] == list(range(1, 13))
    # A number taken by a change that didn't happen is given out again: no gaps.
    assert seen["undone"] == seen["next"] == 13


def test_an_issued_invoice_stays_as_it_was_issued(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        ops, owner, _, _ = await _settled(ops)
        invoice = (await owner.ok("GET", MINE))["items"][0]
        refused = []
        for statement in (
            "UPDATE owner_invoices SET total_paise = total_paise + 1 WHERE public_id = :id",
            "UPDATE owner_invoices SET number = 'FY2000-01/000001' WHERE public_id = :id",
            "DELETE FROM owner_invoices WHERE public_id = :id",
        ):
            try:
                async with ops.app.state.sessionmaker() as db, db.begin():
                    await db.execute(text(statement), {"id": invoice["id"]})
            except DBAPIError as error:
                refused.append("stays as issued" in str(error))
        async with ops.app.state.sessionmaker() as db, db.begin():
            await db.execute(
                text("UPDATE owner_invoices SET pdf_key = pdf_key WHERE public_id = :id"),
                {"id": invoice["id"]},
            )
        return {"refused": refused}

    assert run(scenario) == {"refused": [True, True, True]}


def test_an_expired_link_is_replaced_and_a_cancelled_or_refused_one_waits_for_ops(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        ops, owner, _, _ = await _settled(ops)
        invoice = (await owner.ok("GET", MINE))["items"][0]
        gateway = _gateway(ops)
        now = ops.app.state.clock.now

        async def end(status: LinkStatus) -> None:
            payment = await _link_of(ops, invoice["id"])
            assert payment.provider_link_id is not None
            link = GatewayLink(payment.provider_link_id, None, 154_000, 0, status, "")
            answer = await _send(
                ops, gateway.link_webhook(f"payment_link.{status}", link, at=now())
            )
            assert answer.status_code == 200, answer.text
            await run_due_jobs(ops.app)

        async def pay_link() -> str | None:
            found = (await owner.ok("GET", MINE))["items"][0]["pay"]
            return None if found is None else str(found["url"])

        first = await pay_link()
        await end(LinkStatus.EXPIRED)
        replaced = await pay_link()
        await end(LinkStatus.CANCELLED)
        seen: dict[str, Any] = {
            "first": first is not None,
            "replaced": replaced not in {None, first},
            "cancelled": await pay_link(),
        }
        ask = f"/v1/ops/invoices/{invoice['id']}/payment-link"
        seen["asked"] = (await ops.call("POST", ask)).status_code
        await run_due_jobs(ops.app)
        seen["after asking"] = await pay_link() is not None
        seen["asked again"] = (await ops.call("POST", ask)).json()["code"]
        await end(LinkStatus.CANCELLED)
        gateway.refuses_links = True
        assert (await ops.call("POST", ask)).status_code == 202
        await run_due_jobs(ops.app)
        gateway.refuses_links = False
        seen["refused"] = await pay_link()
        refused = await _link_of(ops, invoice["id"])
        seen["refused ended"] = (
            refused.link_ended_at is not None and refused.provider_link_id is None
        )
        return seen

    assert run(scenario) == {
        "first": True,
        "replaced": True,
        "cancelled": None,
        "asked": 202,
        "after asking": True,
        "asked again": "INVALID_TRANSITION",
        "refused": None,
        "refused ended": True,
    }


def test_a_link_paid_with_the_wrong_amount_moves_nothing_and_ops_hear_of_it(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        ops, owner, code, _ = await _settled(ops)
        invoice = (await owner.ok("GET", MINE))["items"][0]
        payment = await _link_of(ops, invoice["id"])
        assert payment.provider_link_id is not None
        gateway = _gateway(ops)
        signed = gateway.link_paid(
            payment.provider_link_id, reference=None, at=ops.app.state.clock.now()
        )
        event = gateway.read_webhook(signed.raw_body)
        assert event is not None
        assert event.link is not None
        assert event.payment is not None
        short = GatewayLink(
            event.link.id, None, 154_000, 100_000, LinkStatus.PAID, event.link.url, event.payment.id
        )
        await _send(
            ops,
            gateway.link_webhook(
                "payment_link.paid", short, at=ops.app.state.clock.now(), payment=event.payment
            ),
        )
        await run_due_jobs(ops.app)
        issues = (await ops.ok("GET", "/v1/ops/reconciliation/issues"))["items"]
        return {
            "status": (await owner.ok("GET", MINE))["items"][0]["status"],
            "issues": [
                (item["kind"], item["booking"]) for item in issues if item["booking"] == code
            ],
            "owed": (await _balances(ops, code))["owner_receivable"],
        }

    seen = run(scenario)

    assert seen["status"] == "issued"
    assert seen["issues"] == [("link_mismatch", seen["issues"][0][1])]
    assert seen["owed"] == 154_000


def test_an_owners_payment_is_never_a_students(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, beds=1)
        student, code, _ = await _paid(ops, listing)
        await ops.ok("POST", f"/v1/ops/bookings/{code}/confirm", json=REASON)
        ops.app.state.clock.set(MOVED_IN)
        student = await _again(student)
        await student.ok("POST", f"/v1/bookings/{code}/check-in")
        ops.app.state.clock.advance(timedelta(hours=24))
        async with ops.app.state.sessionmaker() as db, db.begin():
            await enqueue(db, CHECK_WINDOWS, {}, clock=ops.app.state.clock)
        await run_due_jobs(ops.app)
        ops = await _again(ops, kind=SessionKind.STAFF)
        owner = await as_owner(ops, listing["owner"])
        invoice = (await owner.ok("GET", MINE))["items"][0]
        await owner.ok("POST", f"{MINE}/{invoice['id']}/test-payment")
        await run_due_jobs(ops.app)
        student = await _again(student)
        payments = (await ops.ok("GET", f"/v1/ops/bookings/{code}/payments"))["items"]
        owners = next(item for item in payments if item["purpose"] == PaymentPurpose.OWNER_INVOICE)
        return {
            "student sees": [
                item["amountPaise"]
                for item in (await student.ok("GET", f"/v1/bookings/{code}/payments"))["items"]
            ],
            "ops see": sorted(
                (item["purpose"], item["status"], item["refundablePaise"]) for item in payments
            ),
            "refund it": (await _ask(ops, owners["id"], 100)).json()["code"],
        }

    assert run(scenario) == {
        "student sees": [200_000],
        # Ops may still give a student's token back; an owner's payment, never from here.
        "ops see": [("owner_invoice", "captured", 0), ("token", "captured", 200_000)],
        "refund it": "INVALID_TRANSITION",
    }
