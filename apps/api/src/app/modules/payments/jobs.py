"""The payments module's job handlers (steps 6.2 and 6.3, ADRs 0057 and 0059), registered in
app/jobs.py with what each needs from outside."""

import uuid
from typing import TYPE_CHECKING

import structlog

from app.modules.booking.service import REFUND_DUE
from app.modules.invoices.service import BALANCE_DUE
from app.modules.payments.service import (
    CHECK_STUCK,
    MAKE_LINK,
    MATCH_SETTLEMENTS,
    PROCESS_EVENT,
    REFUND_TEXT,
    SEND_REFUND,
    InvoiceLinks,
    PaymentWebhooks,
    Reconciliation,
    Refunds,
)

if TYPE_CHECKING:
    from app.core.outbox import JobContext, JobHandler, JobPayload
    from app.core.texts import Texts
    from app.modules.payments.ports import PaymentGateway

__all__ = [
    "BALANCE_DUE",
    "CHECK_STUCK",
    "MAKE_LINK",
    "MATCH_SETTLEMENTS",
    "PROCESS_EVENT",
    "REFUND_DUE",
    "REFUND_TEXT",
    "SEND_REFUND",
    "balance_due_handler",
    "check_stuck_handler",
    "make_link_handler",
    "match_settlements_handler",
    "process_event",
    "refund_due",
    "refund_text_handler",
    "send_refund_handler",
]

logger = structlog.stdlib.get_logger(__name__)


async def process_event(context: JobContext, payload: JobPayload) -> None:
    await PaymentWebhooks(context.session, context.clock).process(int(str(payload["event"])))


async def refund_due(context: JobContext, payload: JobPayload) -> None:
    """A booking's change gives money back: saved here, and sent by a job of its own."""
    await Refunds(context.session, context.clock).due(
        uuid.UUID(str(payload["booking"])),
        amount_paise=int(str(payload["amountPaise"])),
        reason=str(payload["reason"]),
    )


def send_refund_handler(gateway: PaymentGateway) -> JobHandler:
    async def handle(context: JobContext, payload: JobPayload) -> None:
        await Refunds(context.session, context.clock).send(
            gateway, uuid.UUID(str(payload["refund"]))
        )

    return handle


def refund_text_handler(texts: Texts) -> JobHandler:
    async def handle(context: JobContext, payload: JobPayload) -> None:
        found = await Refunds(context.session, context.clock).text_for(
            uuid.UUID(str(payload["refund"]))
        )
        if found is None:
            logger.info("no refund text to send")
            return
        phone, template, values = found
        await texts.send(phone, template, values)

    return handle


def balance_due_handler(gateway: PaymentGateway) -> JobHandler:
    """An invoice was issued with something left to pay: the payment its link will be for."""

    async def handle(context: JobContext, payload: JobPayload) -> None:
        await InvoiceLinks(context.session, context.clock).due(
            gateway.name, uuid.UUID(str(payload["invoice"]))
        )

    return handle


def make_link_handler(gateway: PaymentGateway) -> JobHandler:
    async def handle(context: JobContext, payload: JobPayload) -> None:
        await InvoiceLinks(context.session, context.clock).send(
            gateway, uuid.UUID(str(payload["payment"]))
        )

    return handle


def check_stuck_handler(gateway: PaymentGateway) -> JobHandler:
    async def handle(context: JobContext, payload: JobPayload) -> None:
        _ = payload
        await Reconciliation(context.session, context.clock).check_stuck(gateway)

    return handle


def match_settlements_handler(gateway: PaymentGateway) -> JobHandler:
    async def handle(context: JobContext, payload: JobPayload) -> None:
        _ = payload
        await Reconciliation(context.session, context.clock).match_settlements(gateway)

    return handle
