"""The invoices module's job handlers (step 6.5, ADR 0061), registered in app/jobs.py with what
each needs from outside."""

import uuid
from typing import TYPE_CHECKING

import structlog

from app.modules.invoices.service import (
    BALANCE_DUE,
    INVOICE_TEXT,
    RENDER_PDF,
    InvoicePdfs,
    OwnerInvoices,
)

if TYPE_CHECKING:
    from app.core.outbox import JobContext, JobHandler, JobPayload
    from app.core.texts import Texts
    from app.modules.invoices.pdf import InvoiceSeller
    from app.modules.media.ports import ObjectStorage
    from app.modules.media.service import Buckets

__all__ = [
    "BALANCE_DUE",
    "INVOICE_TEXT",
    "RENDER_PDF",
    "invoice_text_handler",
    "render_pdf_handler",
]

logger = structlog.stdlib.get_logger(__name__)


def render_pdf_handler(
    storage: ObjectStorage, buckets: Buckets, seller: InvoiceSeller
) -> JobHandler:
    async def handle(context: JobContext, payload: JobPayload) -> None:
        await InvoicePdfs(context.session, storage, buckets, seller).make(
            uuid.UUID(str(payload["invoice"]))
        )

    return handle


def invoice_text_handler(texts: Texts) -> JobHandler:
    async def handle(context: JobContext, payload: JobPayload) -> None:
        found = await OwnerInvoices(context.session, context.clock).text_for(
            uuid.UUID(str(payload["invoice"]))
        )
        if found is None:
            logger.info("no invoice text to send")
            return
        phone, template, values = found
        await texts.send(phone, template, values)

    return handle
