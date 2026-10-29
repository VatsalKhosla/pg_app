"""The compliance module's background jobs, registered in app/jobs.py with what they need: every
module's export part, the retention rules, and the texts sender grievances use."""

from typing import TYPE_CHECKING, Final

import structlog

from app.modules.compliance.retention import run_retention
from app.modules.compliance.service import (
    BUILD_EXPORT,
    GRIEVANCE_TEXT,
    GrievanceTexts,
    build_export,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.core.outbox import JobContext, JobHandler, JobPayload
    from app.core.texts import Texts
    from app.modules.compliance.retention import RetentionRule
    from app.modules.compliance.service import Exporter

RETENTION: Final = "compliance.retention"

__all__ = [
    "BUILD_EXPORT",
    "GRIEVANCE_TEXT",
    "RETENTION",
    "build_export_handler",
    "grievance_text_handler",
    "retention_handler",
]

logger = structlog.stdlib.get_logger(__name__)


def build_export_handler(exporters: Sequence[Exporter]) -> JobHandler:
    async def handle(context: JobContext, payload: JobPayload) -> None:
        await build_export(
            context.session, context.clock, int(payload["data_request_id"]), exporters
        )

    return handle


def retention_handler(rules: Sequence[RetentionRule]) -> JobHandler:
    async def handle(context: JobContext, _payload: JobPayload) -> None:
        await run_retention(context.session, context.clock, rules)

    return handle


def grievance_text_handler(texts: Texts) -> JobHandler:
    """A text to a signed-in complainant about their grievance."""

    async def handle(context: JobContext, payload: JobPayload) -> None:
        template = str(payload["template"])
        found = await GrievanceTexts(context.session).message(str(payload["ticket"]), template)
        if found is None:
            logger.info("grievance text no longer applies", template=template)
            return
        phone, values = found
        await texts.send(phone, template, values)

    return handle
