"""The visits module's job handlers, registered in app/jobs.py with the texts sender they use."""

import uuid
from typing import TYPE_CHECKING

import structlog

from app.modules.visits.service import TEXT, VisitTexts

if TYPE_CHECKING:
    from app.core.outbox import JobContext, JobHandler, JobPayload
    from app.core.texts import Texts

__all__ = ["TEXT", "text_handler"]

logger = structlog.stdlib.get_logger(__name__)


def text_handler(texts: Texts) -> JobHandler:
    """A text to the student about their visit, unless the visit has moved on since it was
    queued: cancelled, booked for another time, or done."""

    async def handle(context: JobContext, payload: JobPayload) -> None:
        template = str(payload["template"])
        found = await VisitTexts(context.session).message(
            uuid.UUID(str(payload["visit"])), template, str(payload["at"])
        )
        if found is None:
            logger.info("visit text no longer applies", template=template)
            return
        phone, values = found
        await texts.send(phone, template, values)

    return handle
