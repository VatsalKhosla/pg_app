"""Every background job kind and periodic schedule the worker runs (a composition root).

Modules add their handlers and schedules here as they arrive (booking timeouts in Phase 5,
payment reconciliation in Phase 6, ...). Two lists here are read as documents too: what a
person's data export holds, and the retention schedule.
"""

from datetime import time, timedelta
from typing import Final

from app.core.idempotency import IDEMPOTENCY_CLEANUP, delete_expired_keys
from app.core.outbox import OUTBOX_CLEANUP, JobRegistry, delete_finished_jobs
from app.core.scheduler import DailyAt, Every, ScheduledJob
from app.modules.compliance.jobs import (
    BUILD_EXPORT,
    RETENTION,
    build_export_handler,
    retention_handler,
)
from app.modules.compliance.retention import RetentionRule
from app.modules.compliance.service import data_requests_part, expire_exports
from app.modules.identity.service import (
    delete_finished_sessions,
    delete_old_challenges,
    personal_data,
)

# A person's data export (DPDP): one part from every module that holds personal data. A module
# that starts keeping personal data adds its part here.
EXPORTERS: Final = (personal_data, data_requests_part)

# The retention schedule (DPDP: no longer than needed). A module that starts keeping personal data
# adds its rule here; periods still to be decided by the founders are noted in ADR 0018.
RETENTION_RULES: Final = (
    RetentionRule(
        "sessions",
        "Sessions, with their IP address and user agent: 30 days after they end or expire",
        delete_finished_sessions,
    ),
    RetentionRule(
        "sign_in_codes",
        "Sign-in codes, with the phone number, IP address and user agent: after 7 days",
        delete_old_challenges,
    ),
    RetentionRule("data_exports", "Data export files: 7 days after they are ready", expire_exports),
)

SCHEDULES: Final = (
    ScheduledJob(name=OUTBOX_CLEANUP, kind=OUTBOX_CLEANUP, schedule=DailyAt(time(3, 0))),
    ScheduledJob(
        name=IDEMPOTENCY_CLEANUP, kind=IDEMPOTENCY_CLEANUP, schedule=Every(timedelta(hours=1))
    ),
    ScheduledJob(name=RETENTION, kind=RETENTION, schedule=DailyAt(time(3, 30))),
)


def build_registry() -> JobRegistry:
    registry = JobRegistry()
    registry.register(OUTBOX_CLEANUP, delete_finished_jobs)
    registry.register(IDEMPOTENCY_CLEANUP, delete_expired_keys)
    registry.register(BUILD_EXPORT, build_export_handler(EXPORTERS))
    registry.register(RETENTION, retention_handler(RETENTION_RULES))
    return registry
