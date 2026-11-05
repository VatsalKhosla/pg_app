"""A gateway's webhooks (ARCHITECTURE §9.3; step 6.2, ADR 0057).

``receive`` is what the gateway waits for, and Razorpay waits 5 seconds: check the signature on the
raw body, store the event once, queue a job in the same transaction, and answer. ``process`` is the
job: it finds the order the event is about and settles it, as a checkout would, and marks the event
done in the job's transaction. An event we don't act on, or that's about no order of ours, is kept
and goes no further.
"""

import hashlib
from typing import TYPE_CHECKING, Final

import structlog
from opentelemetry import metrics

from app.core import audit
from app.core.outbox import enqueue
from app.modules.payments.domain.payments import PaymentPurpose, Settlement
from app.modules.payments.domain.webhooks import (
    kept_payload,
    link_in,
    payment_in,
    refund_in,
    too_old,
)
from app.modules.payments.errors import WebhookInvalidError
from app.modules.payments.repository import PaymentRepository
from app.modules.payments.schemas import WebhookReceipt
from app.modules.payments.service.invoice_links import InvoiceLinks
from app.modules.payments.service.refunds import Refunds
from app.modules.payments.service.settlement import PaymentSettlements

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.clock import Clock
    from app.modules.payments.domain.payments import GatewayPayment
    from app.modules.payments.ports import PaymentGateway

PROCESS_EVENT: Final = "payments.process_event"

logger = structlog.stdlib.get_logger(__name__)

_received = metrics.get_meter("app.payments").create_counter(
    "payments.webhooks", description="Webhooks that reached the API, by what became of them"
)


def _refused(why: str) -> WebhookInvalidError:
    logger.warning("a webhook was refused", why=why)
    _received.add(1, {"outcome": why})
    return WebhookInvalidError()


class PaymentWebhooks:
    def __init__(self, db: AsyncSession, clock: Clock) -> None:
        self._db = db
        self._clock = clock
        self._payments = PaymentRepository(db)
        self._settlements = PaymentSettlements(db, clock)
        self._refunds = Refunds(db, clock)
        self._links = InvoiceLinks(db, clock)

    async def receive(
        self, gateway: PaymentGateway, *, raw_body: bytes, signature: str, event_id: str
    ) -> WebhookReceipt:
        """Stored and queued, or seen before. 400 WEBHOOK_INVALID for a bad signature, what isn't
        an event, or a replay too old for the gateway to be retrying."""
        if not gateway.verify_webhook(raw_body=raw_body, signature=signature):
            raise _refused("bad_signature")
        event = gateway.read_webhook(raw_body)
        if event is None:
            raise _refused("not_an_event")
        now = self._clock.now()
        if too_old(event, now):
            raise _refused("too_old")
        async with self._db.begin():
            stored = await self._payments.add_event_once(
                provider=gateway.name,
                # The body says the same each time it's sent, should the header ever be missing.
                event_id=event_id or f"body:{hashlib.sha256(raw_body).hexdigest()}",
                kind=event.kind,
                payload=kept_payload(event),
                received_at=now,
            )
            if stored is not None:
                await enqueue(
                    self._db,
                    PROCESS_EVENT,
                    {"event": stored},
                    clock=self._clock,
                    dedupe_key=f"{PROCESS_EVENT}:{stored}",
                )
        _received.add(1, {"outcome": "duplicate" if stored is None else "new"})
        return WebhookReceipt(new=stored is not None)

    async def process(self, event_id: int) -> None:
        """Inside the job's transaction. Running it twice changes nothing the second time."""
        event = await self._payments.event(event_id)
        if event is None or event.processed_at is not None:
            return
        event.processed_at = self._clock.now()
        if event.payload.get("unreadable") is True:
            logger.error("a webhook's payment couldn't be read", event_type=event.event_type)
            event.error = "unreadable"
            return
        found = payment_in(event.payload)
        refund = refund_in(event.payload)
        link = link_in(event.payload)
        if refund is not None:
            event.error = await self._refunds.settle(event.provider, refund, found)
        elif link is not None:
            event.error = await self._links.settle(event.provider, link, found)
        elif found is not None:
            event.error = await self._payment(event.provider, event.event_type, found)

    async def _payment(self, provider: str, kind: str, found: GatewayPayment) -> str | None:
        """An order's payment, as a checkout would settle it. Why it moved nothing, when someone
        should look."""
        payment = (
            None
            if found.order_id is None
            else await self._payments.by_order(provider, found.order_id)
        )
        if payment is None:
            # Another environment's, on the same Razorpay account, or a payment link's, whose
            # order we learn as the link is paid.
            logger.info("a webhook about no order of ours", event_type=kind)
            return "unknown_order"
        if payment.purpose != PaymentPurpose.TOKEN:
            return None  # a link's payment: its link's own event moves it
        settled = await self._settlements.apply(payment, found, by=audit.SYSTEM)
        return "mismatch" if settled is Settlement.MISMATCH else None
