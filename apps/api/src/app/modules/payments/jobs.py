"""The payments module's job handlers (step 6.2, ADR 0057), registered in app/jobs.py."""

from typing import TYPE_CHECKING

from app.modules.payments.service import PROCESS_EVENT, PaymentWebhooks

if TYPE_CHECKING:
    from app.core.outbox import JobContext, JobPayload

__all__ = ["PROCESS_EVENT", "process_event"]


async def process_event(context: JobContext, payload: JobPayload) -> None:
    await PaymentWebhooks(context.session, context.clock).process(int(str(payload["event"])))
