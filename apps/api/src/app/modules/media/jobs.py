"""The media module's background jobs, registered in app/jobs.py with the storage they use."""

import uuid
from typing import TYPE_CHECKING

from app.modules.media.service import DISCARD_UPLOAD, PROCESS, discard_upload, process_upload

if TYPE_CHECKING:
    from app.core.outbox import JobContext, JobHandler, JobPayload
    from app.modules.media.ports import ObjectStorage
    from app.modules.media.service import Buckets

__all__ = ["DISCARD_UPLOAD", "PROCESS", "discard_upload_handler", "process_handler"]


def process_handler(storage: ObjectStorage, buckets: Buckets) -> JobHandler:
    async def handle(context: JobContext, payload: JobPayload) -> None:
        await process_upload(
            context.session,
            context.clock,
            storage=storage,
            buckets=buckets,
            media_id=uuid.UUID(str(payload["media_id"])),
        )

    return handle


def discard_upload_handler(storage: ObjectStorage, buckets: Buckets) -> JobHandler:
    async def handle(_context: JobContext, payload: JobPayload) -> None:
        await discard_upload(storage, buckets, uuid.UUID(str(payload["media_id"])))

    return handle
