"""The compliance module's background jobs, registered in app/jobs.py with what they need: every
module's export part, and the retention rules."""

from typing import TYPE_CHECKING, Final

from app.modules.compliance.retention import run_retention
from app.modules.compliance.service import BUILD_EXPORT, build_export

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.core.outbox import JobContext, JobHandler, JobPayload
    from app.modules.compliance.retention import RetentionRule
    from app.modules.compliance.service import Exporter

RETENTION: Final = "compliance.retention"

__all__ = ["BUILD_EXPORT", "RETENTION", "build_export_handler", "retention_handler"]


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
