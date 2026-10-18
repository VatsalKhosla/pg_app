"""Every background job kind and periodic schedule the worker runs (a composition root).

Modules add their handlers and schedules here as they arrive (booking timeouts in Phase 5,
payment reconciliation in Phase 6, ...).
"""

from datetime import time, timedelta
from typing import Final

from app.core.idempotency import IDEMPOTENCY_CLEANUP, delete_expired_keys
from app.core.outbox import OUTBOX_CLEANUP, JobRegistry, delete_finished_jobs
from app.core.scheduler import DailyAt, Every, ScheduledJob

SCHEDULES: Final = (
    ScheduledJob(name=OUTBOX_CLEANUP, kind=OUTBOX_CLEANUP, schedule=DailyAt(time(3, 0))),
    ScheduledJob(
        name=IDEMPOTENCY_CLEANUP, kind=IDEMPOTENCY_CLEANUP, schedule=Every(timedelta(hours=1))
    ),
)


def build_registry() -> JobRegistry:
    registry = JobRegistry()
    registry.register(OUTBOX_CLEANUP, delete_finished_jobs)
    registry.register(IDEMPOTENCY_CLEANUP, delete_expired_keys)
    return registry
