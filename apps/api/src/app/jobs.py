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
from app.modules.booking.jobs import (
    CHECK_WINDOWS,
    CONFIRMATION_TIMEOUTS,
    NOTIFY,
    notify_handler,
    settle_check_windows,
    time_out_confirmations,
)
from app.modules.booking.service import bookings_part
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
from app.modules.inventory.service import ALLOCATIONS_CHANGED
from app.modules.media.jobs import (
    DISCARD_UPLOAD,
    PROCESS,
    discard_upload_handler,
    process_handler,
)
from app.modules.pricing.jobs import CHECK_INTEGRITY, check_integrity_handler
from app.modules.pricing.service import BAND_CHANGED, CAPS_CHANGED, RULES_CHANGED
from app.modules.search.jobs import (
    REFRESH,
    REFRESH_ALL,
    REPRICE,
    band_changed_handler,
    caps_changed_handler,
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
    from app.modules.pricing.occupancy import BedsTaken

# A person's data export (DPDP): one part from every module that holds personal data. A module
# that starts keeping personal data adds its part here.
EXPORTERS: Final = (
    personal_data,
    owner_data,
    data_requests_part,
    visits_part,
    bookings_part,
    grievances_part,
)

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
    # Pricing's integrity alerts: the market as it stands, and last week's quotes (ADR 0043).
    ScheduledJob(name=CHECK_INTEGRITY, kind=CHECK_INTEGRITY, schedule=DailyAt(time(1, 0))),
    # Owners who didn't confirm in time lose the booking, and the student is refunded (§7.5).
    ScheduledJob(
        name=CONFIRMATION_TIMEOUTS,
        kind=CONFIRMATION_TIMEOUTS,
        schedule=Every(timedelta(minutes=5)),
    ),
    # A check window that ended without a dispute settles the booking (§7.5).
    ScheduledJob(name=CHECK_WINDOWS, kind=CHECK_WINDOWS, schedule=Every(timedelta(minutes=5))),
)


def build_registry(
    *,
    storage: ObjectStorage,
    buckets: Buckets,
    web_cache: WebCache,
    texts: Texts,
    analytics: Analytics,
    beds: BedsTaken,
) -> JobRegistry:
    """Every handler, with what it needs from outside: the object storage media jobs use, the
    web app whose cached pages are revalidated, the texts visits, bookings and grievances send,
    where the funnel's server-side steps go, and how full rooms are for the prices search
    keeps."""
    registry = JobRegistry()
    registry.register(OUTBOX_CLEANUP, delete_finished_jobs)
    registry.register(IDEMPOTENCY_CLEANUP, delete_expired_keys)
    registry.register(BUILD_EXPORT, build_export_handler(EXPORTERS))
    registry.register(RETENTION, retention_handler(RETENTION_RULES))
    registry.register(PROCESS, process_handler(storage, buckets))
    registry.register(DISCARD_UPLOAD, discard_upload_handler(storage, buckets))
    # A listing changed, its rooms and rents included: its search entry and price summaries
    # follow (steps 3.1 and 3.2), and the web app's pages for it (step 3.6).
    registry.register(INVENTORY_CHANGED, changed_handler(beds))
    registry.register(LISTING_CHANGED, changed_handler(beds))
    registry.register(REFRESH, refresh_handler(beds))
    registry.register(REFRESH_ALL, refresh_all_handler(beds))
    # Its prices moved: its rules went into force, or its locality's band or the caps changed
    # (step 4.7, ADR 0042).
    registry.register(RULES_CHANGED, changed_handler(beds))
    registry.register(REPRICE, changed_handler(beds))
    registry.register(BAND_CHANGED, band_changed_handler(beds))
    registry.register(CAPS_CHANGED, caps_changed_handler(beds))
    registry.register(CHECK_INTEGRITY, check_integrity_handler)
    # Its beds changed hands: free beds, occupancy and so prices (step 5.1, ADR 0044).
    registry.register(ALLOCATIONS_CHANGED, changed_handler(beds))
    registry.register(REVALIDATE, revalidate_handler(web_cache))
    registry.register(TEXT, text_handler(texts))
    # Bookings (step 5.4, ADR 0048): texts about them, and confirmations not given in time.
    registry.register(NOTIFY, notify_handler(texts))
    registry.register(CONFIRMATION_TIMEOUTS, time_out_confirmations)
    registry.register(CHECK_WINDOWS, settle_check_windows)
    registry.register(GRIEVANCE_TEXT, grievance_text_handler(texts))
    registry.register(ANALYTICS_CAPTURE, capture_handler(analytics))
    return registry
