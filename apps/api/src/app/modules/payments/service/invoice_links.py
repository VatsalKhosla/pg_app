"""Collecting an invoice's balance through a payment link (ARCHITECTURE §9.5; step 6.5, ADR 0061).

The invoices module asks for it as an invoice is issued (its BALANCE_DUE job). A payment is saved
first, then a job of its own asks the gateway for the link, whose reference makes asking twice
safe: no call to the gateway happens inside a change. The gateway's word that the link was paid,
for exactly the balance, captures the payment, posts the money and marks the invoice paid, in one
transaction. An expired link is replaced; a cancelled or refused one waits for ops to ask again.
"""

import uuid
from typing import TYPE_CHECKING, Final

import structlog

from app.core import audit
from app.core.errors import InvalidTransitionError, NotFoundError
from app.core.outbox import enqueue
from app.modules.invoices.domain.invoices import InvoiceStatus
from app.modules.invoices.service import BALANCE_DUE, OwnerInvoices
from app.modules.ledger.domain.ledger import owner_paid
from app.modules.ledger.service import Ledger
from app.modules.payments.domain.links import (
    MIN_LINK_PAISE,
    LinkReading,
    LinkStatus,
    link_reference,
    read_link,
)
from app.modules.payments.domain.payments import PaymentMode, PaymentPurpose, PaymentStatus
from app.modules.payments.domain.reconciliation import IssueKind
from app.modules.payments.errors import PaymentGatewayRefusedError
from app.modules.payments.repository import PaymentRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.modules.payments.adapters.fake import FakeGateway, SignedWebhook
    from app.modules.payments.domain.links import GatewayLink
    from app.modules.payments.domain.payments import GatewayPayment
    from app.modules.payments.models import Payment
    from app.modules.payments.ports import PaymentGateway

MAKE_LINK: Final = "payments.make_link"

logger = structlog.stdlib.get_logger(__name__)


class InvoiceLinks:
    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._db = db
        self._clock = clock
        self._payments = PaymentRepository(db)
        self._invoices = OwnerInvoices(db, clock)
        self._ledger = Ledger(db, clock)

    async def due(self, provider: str, invoice_id: uuid.UUID) -> None:
        """The job an issued invoice asks for: the payment its link will be for, saved, and a job
        to ask the gateway for the link. Nothing new while a link can be paid."""
        balance = await self._invoices.balance(invoice_id)
        if balance is None or balance.status is InvoiceStatus.PAID:
            return
        if balance.balance_due_paise < MIN_LINK_PAISE:
            logger.error(
                "an invoice's balance is too small for a payment link", invoice=balance.number
            )
            return
        if await self._payments.open_link_of(balance.id) is not None:
            return
        ended = await self._payments.ended_links_of(balance.id)
        payment = await self._payments.add_once(
            booking_id=balance.booking_id,
            purpose=PaymentPurpose.OWNER_INVOICE,
            mode=PaymentMode.PAYMENT,
            provider=provider,
            key=f"invoice:{balance.public_id}:{ended + 1}",
            amount_paise=balance.balance_due_paise,
            made_at=self._clock.now(),
            invoice_id=balance.id,
        )
        await enqueue(
            self._db,
            MAKE_LINK,
            {"payment": str(payment.public_id)},
            clock=self._clock,
            dedupe_key=f"{MAKE_LINK}:{payment.public_id}",
        )

    async def send(self, gateway: PaymentGateway, payment_id: uuid.UUID) -> None:
        """The link, from the gateway, inside the job's transaction with nothing locked during the
        call. What may pass raises, so the job tries again; a refusal ends this payment's link."""
        payment = await self._payments.by_public_id(payment_id)
        if (
            payment is None
            or payment.invoice_id is None
            or payment.provider_link_id is not None
            or payment.link_ended_at is not None
        ):
            return
        balance = await self._invoices.balance_by_id(payment.invoice_id)
        if balance.status is InvoiceStatus.PAID:
            return
        if payment.provider != gateway.name:
            await self._end(
                payment, "payment_link.refused", note="Another gateway takes payments now."
            )
            return
        try:
            link = await gateway.create_payment_link(
                amount_paise=payment.amount_paise,
                reference=link_reference(payment.public_id),
                description=f"Invoice {balance.number}",
                notes={
                    "invoice": balance.number,
                    "booking": balance.booking_code,
                    "purpose": PaymentPurpose.OWNER_INVOICE,
                },
            )
        except PaymentGatewayRefusedError as error:
            logger.error("the gateway refused an invoice's payment link", invoice=balance.number)
            await self._end(payment, "payment_link.refused", note=str(error))
            return
        locked = await self._payments.by_public_id(payment_id, lock=True)
        if locked is None or locked.provider_link_id is not None:
            return
        locked.provider_link_id = link.id
        await self._invoices.offer(balance.id, provider=gateway.name, url=link.url)
        await self._record(locked, "payment_link.made")

    async def settle(
        self, provider: str, link: GatewayLink, found: GatewayPayment | None
    ) -> str | None:
        """A gateway's word about a link, inside the job's transaction. Why it moved nothing, when
        someone should look."""
        payment = await self._payments.by_link(provider, link.id)
        if payment is None or payment.invoice_id is None:
            logger.info("a payment link that isn't ours")
            return "unknown_link"
        if payment.status == PaymentStatus.CAPTURED:
            return None
        match read_link(link, found, amount_paise=payment.amount_paise):
            case LinkReading.PAID:
                assert found is not None  # noqa: S101 - read_link said paid
                await self._paid(payment, found)
            case LinkReading.MISMATCH:
                balance = await self._invoices.balance_by_id(payment.invoice_id)
                logger.error("a payment link was paid, but not as asked", invoice=balance.number)
                await self._record(payment, "payment.mismatch")
                await self._payments.add_issue_once(
                    kind=IssueKind.LINK_MISMATCH,
                    provider=provider,
                    reference=link.id,
                    booking_code=balance.booking_code,
                    amount_paise=link.amount_paid_paise,
                    detail=f"Invoice {balance.number}: the gateway says its link was paid, but not "
                    f"exactly the {payment.amount_paise} paise asked for.",
                    found_at=self._clock.now(),
                )
                return "mismatch"
            case LinkReading.ENDED:
                await self._ended(payment, link)
            case LinkReading.NOTHING_YET:
                pass
        return None

    async def ask(self, actor: Actor, invoice_id: uuid.UUID) -> None:
        """Ops ask for a link again, after one was cancelled or refused. 409 INVALID_TRANSITION once
        it's paid, or while a link can still be paid."""
        async with self._db.begin():
            balance = await self._invoices.balance(invoice_id)
            if balance is None:
                raise NotFoundError
            if balance.status is InvoiceStatus.PAID:
                raise InvalidTransitionError("This invoice is paid.")
            if await self._payments.open_link_of(balance.id) is not None:
                raise InvalidTransitionError("This invoice has a payment link already.")
            # Each ask is its own job: the job finds nothing to do if a link came in between.
            await enqueue(
                self._db,
                BALANCE_DUE,
                {"invoice": str(invoice_id)},
                clock=self._clock,
                dedupe_key=f"{BALANCE_DUE}:{invoice_id}:asked:{uuid.uuid4()}",
            )
            await audit.record(
                self._db,
                clock=self._clock,
                actor=audit.Actor("staff", actor.user_id),
                action="invoice.link_asked",
                entity_type="owner_invoice",
                entity_id=str(invoice_id),
                details={"number": balance.number},
            )

    async def test_bank(
        self, gateway: FakeGateway, actor: Actor, invoice_id: uuid.UUID
    ) -> SignedWebhook:
        """The fake gateway's bank pays the owner's own invoice's link: the webhook it sends."""
        async with self._db.begin():
            balance = await self._invoices.own_balance(actor, invoice_id)
            payment = await self._payments.open_link_of(balance.id)
        if (
            balance.status is InvoiceStatus.PAID
            or payment is None
            or payment.provider_link_id is None
            or payment.provider != gateway.name
        ):
            raise InvalidTransitionError("This invoice has no payment link to pay.")
        return gateway.link_paid(
            payment.provider_link_id,
            reference=link_reference(payment.public_id),
            at=self._clock.now(),
        )

    async def _paid(self, payment: Payment, found: GatewayPayment) -> None:
        assert payment.invoice_id is not None  # noqa: S101 - a link's payment
        payment.status = PaymentStatus.CAPTURED
        payment.provider_payment_id = found.id
        payment.provider_order_id = payment.provider_order_id or found.order_id
        payment.captured_at = self._clock.now()
        balance = await self._invoices.balance_by_id(payment.invoice_id)
        await self._record(payment, "payment.captured")
        await self._ledger.post(
            owner_paid(payment.amount_paise),
            key=f"owner_paid:{payment.public_id}",
            booking_id=payment.booking_id,
            booking_code=balance.booking_code,
            payment_id=payment.id,
            memo=balance.number,
        )
        await self._invoices.paid(payment.invoice_id, by=audit.SYSTEM)

    async def _ended(self, payment: Payment, link: GatewayLink) -> None:
        """The link can't be paid any more. An expired one is replaced at once."""
        assert payment.invoice_id is not None  # noqa: S101 - a link's payment
        if payment.link_ended_at is not None:
            return
        payment.link_ended_at = self._clock.now()
        await self._invoices.withdraw(payment.invoice_id, url=link.url or None)
        await self._record(payment, f"payment_link.{link.status}")
        balance = await self._invoices.balance_by_id(payment.invoice_id)
        if link.status is LinkStatus.EXPIRED and balance.status is InvoiceStatus.ISSUED:
            await enqueue(
                self._db,
                BALANCE_DUE,
                {"invoice": str(balance.public_id)},
                clock=self._clock,
                dedupe_key=f"{BALANCE_DUE}:{balance.public_id}:after:{payment.public_id}",
            )

    async def _end(self, payment: Payment, action: str, *, note: str) -> None:
        locked = await self._payments.by_public_id(payment.public_id, lock=True)
        if locked is None or locked.link_ended_at is not None:
            return
        locked.link_ended_at = self._clock.now()
        await self._record(locked, action, note=note)

    async def _record(self, payment: Payment, action: str, *, note: str | None = None) -> None:
        details: dict[str, object] = {
            "amountPaise": payment.amount_paise,
            "purpose": payment.purpose,
        }
        if note is not None:
            details["note"] = note
        await audit.record(
            self._db,
            clock=self._clock,
            actor=audit.SYSTEM,
            action=action,
            entity_type="payment",
            entity_id=str(payment.public_id),
            details=details,
        )
