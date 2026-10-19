"""Every background job kind and periodic schedule the worker runs (a composition root).

Modules add their handlers and schedules here as they arrive (booking timeouts in Phase 5,
payment reconciliation in Phase 6, ...).
"""

from datetime import time, timedelta
from typing import Final

from app.core.idempotency import IDEMPOTENCY_CLEANUP, delete_expired_keys
from app.core.outbox import OUTBOX_CLEANUP, JobRegistry, delete_finished_jobs
from app.core.scheduler import DailyAt, Every, ScheduledJob
from app.modules.identity.jobs import (
    OTP_CLEANUP,
    SESSIONS_CLEANUP,
    delete_finished_sessions_job,
    delete_old_challenges_job,
)

SCHEDULES: Final = (
    ScheduledJob(name=OUTBOX_CLEANUP, kind=OUTBOX_CLEANUP, schedule=DailyAt(time(3, 0))),
    ScheduledJob(
        name=IDEMPOTENCY_CLEANUP, kind=IDEMPOTENCY_CLEANUP, schedule=Every(timedelta(hours=1))
    ),
    ScheduledJob(name=SESSIONS_CLEANUP, kind=SESSIONS_CLEANUP, schedule=DailyAt(time(3, 30))),
    ScheduledJob(name=OTP_CLEANUP, kind=OTP_CLEANUP, schedule=DailyAt(time(3, 45))),
)


def build_registry() -> JobRegistry:
    registry = JobRegistry()
    registry.register(OUTBOX_CLEANUP, delete_finished_jobs)
    registry.register(IDEMPOTENCY_CLEANUP, delete_expired_keys)
    registry.register(SESSIONS_CLEANUP, delete_finished_sessions_job)
    registry.register(OTP_CLEANUP, delete_old_challenges_job)
    return registry
