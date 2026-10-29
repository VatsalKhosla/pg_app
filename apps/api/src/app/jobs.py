"""Every background job kind and periodic schedule the worker runs (a composition root).

Modules add their handlers and schedules here as they arrive (booking timeouts in Phase 5,
payment reconciliation in Phase 6, ...). Two lists here are read as documents too: what a
person's data export holds, and the retention schedule.
"""

from datetime import time, timedelta
from typing import TYPE_CHECKING, Final

from app.core.analytics import ANALYTICS_CAPTURE, capture_handler
from app.core.idempotency import IDEMPOTENCY_CLEANUP, delete_expired_keys
from app.core.outbox import OUTBOX_CLEANUP, JobRegistry, delete_finished_jobs
from app.core.scheduler import DailyAt, Every, ScheduledJob
from app.core.web_cache import REVALIDATE, revalidate_handler
from app.modules.catalog.service import INVENTORY_CHANGED, LISTING_CHANGED, owner_data
from app.modules.compliance.jobs import (
    BUILD_EXPORT,
    GRIEVANCE_TEXT,
    RETENTION,
    build_export_handler,
    grievance_text_handler,
    retention_handler,
)
from app.modules.compliance.retention import RetentionRule
from app.modules.compliance.service import data_requests_part, expire_exports, grievances_part
from app.modules.identity.service import (
    delete_finished_sessions,
    delete_old_challenges,
    personal_data,
)
from app.modules.media.jobs import (
    DISCARD_UPLOAD,
    PROCESS,
    discard_upload_handler,
    process_handler,
)
from app.modules.search.jobs import (
    REFRESH,
    REFRESH_ALL,
    changed_handler,
    refresh_all_handler,
    refresh_handler,
)
from app.modules.visits.jobs import TEXT, text_handler
from app.modules.visits.service import visits_part

if TYPE_CHECKING:
    from app.core.analytics import Analytics
    from app.core.texts import Texts
    from app.core.web_cache import WebCache
    from app.modules.media.ports import ObjectStorage
    from app.modules.media.service import Buckets

# A person's data export (DPDP): one part from every module that holds personal data. A module
# that starts keeping personal data adds its part here.
EXPORTERS: Final = (personal_data, owner_data, data_requests_part, visits_part, grievances_part)

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
    # Just after midnight, so the price months roll forward as soon as a new one starts.
    ScheduledJob(name=REFRESH_ALL, kind=REFRESH_ALL, schedule=DailyAt(time(0, 30))),
)


def build_registry(
    *,
    storage: ObjectStorage,
    buckets: Buckets,
    web_cache: WebCache,
    texts: Texts,
    analytics: Analytics,
) -> JobRegistry:
    """Every handler, with what it needs from outside: the object storage media jobs use, the
    web app whose cached pages are revalidated, the texts visits and grievances send, and where
    the funnel's server-side steps go."""
    registry = JobRegistry()
    registry.register(OUTBOX_CLEANUP, delete_finished_jobs)
    registry.register(IDEMPOTENCY_CLEANUP, delete_expired_keys)
    registry.register(BUILD_EXPORT, build_export_handler(EXPORTERS))
    registry.register(RETENTION, retention_handler(RETENTION_RULES))
    registry.register(PROCESS, process_handler(storage, buckets))
    registry.register(DISCARD_UPLOAD, discard_upload_handler(storage, buckets))
    # A listing changed, its rooms and rents included: its search entry and price summaries
    # follow (steps 3.1 and 3.2), and the web app's pages for it (step 3.6).
    registry.register(INVENTORY_CHANGED, changed_handler)
    registry.register(LISTING_CHANGED, changed_handler)
    registry.register(REFRESH, refresh_handler)
    registry.register(REFRESH_ALL, refresh_all_handler)
    registry.register(REVALIDATE, revalidate_handler(web_cache))
    registry.register(TEXT, text_handler(texts))
    registry.register(GRIEVANCE_TEXT, grievance_text_handler(texts))
    registry.register(ANALYTICS_CAPTURE, capture_handler(analytics))
    return registry
