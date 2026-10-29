"""Product analytics from the server (ARCHITECTURE §3; step 3.9, ADR 0035).

The booking funnel runs search → PG view → visit request → visit done → reservation. The first
steps happen in the student's browser, which reports them itself; the later ones happen
elsewhere, such as a field agent finishing a visit on their phone, so the API reports those. It
uses the anonymous id the student's browser had when they asked (never their account), so
PostHog joins the steps into one funnel.

Events are personless (``$process_person_profile`` false), with GeoIP off and no personal data.
A job sends each one through the outbox, so a slow or unreachable PostHog never slows a request.
Each event has a uuid fixed when it's queued, which PostHog uses to drop repeats, so a retried
job still counts once. Without a project key nothing is sent.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Final, Protocol

import structlog

from app.core.outbox import enqueue

if TYPE_CHECKING:
    import httpx
    from pydantic import SecretStr
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.clock import Clock
    from app.core.outbox import JobContext, JobHandler, JobPayload

ANALYTICS_CAPTURE: Final = "analytics.capture"
_BATCH_PATH: Final = "/batch/"
# Says which side of the platform sent an event; the web app's say "web".
_LIBRARY: Final = "api"

type Property = str | int | float | bool | None

logger = structlog.stdlib.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class AnalyticsEvent:
    uuid: str
    name: str
    distinct_id: str
    properties: Mapping[str, Property]
    timestamp: datetime


class AnalyticsError(Exception):
    """PostHog didn't take the event; the outbox tries the job again later."""


class Analytics(Protocol):
    async def capture(self, event: AnalyticsEvent) -> None:
        """Record ``event``; raise if it wasn't taken, so the job is tried again."""


class NoAnalytics:
    """No project key (local development, tests, or before the founders' account): nothing is
    sent."""

    async def capture(self, event: AnalyticsEvent) -> None:
        logger.debug("analytics off", analytics_event=event.name)


class PostHogAnalytics:
    """PostHog's batch capture endpoint, one event a request. Any answer but 200 is an error."""

    def __init__(self, http: httpx.AsyncClient, *, host: str, project_key: SecretStr) -> None:
        self._http = http
        self._url = f"{host.rstrip('/')}{_BATCH_PATH}"
        self._project_key = project_key

    async def capture(self, event: AnalyticsEvent) -> None:
        body = {
            "api_key": self._project_key.get_secret_value(),
            "batch": [
                {
                    "uuid": event.uuid,
                    "event": event.name,
                    "distinct_id": event.distinct_id,
                    "timestamp": event.timestamp.isoformat(),
                    "properties": {
                        **event.properties,
                        "$process_person_profile": False,
                        "$geoip_disable": True,
                        "$lib": _LIBRARY,
                    },
                }
            ],
        }
        response = await self._http.post(self._url, json=body)
        if response.status_code != 200:
            msg = f"PostHog answered {response.status_code}"
            raise AnalyticsError(msg)


async def record(
    session: AsyncSession,
    *,
    clock: Clock,
    name: str,
    distinct_id: uuid.UUID,
    properties: Mapping[str, Property],
    dedupe_key: str,
) -> None:
    """Queue ``name`` for the browser that had ``distinct_id``, in the caller's transaction: it's
    sent only if that commits, and once per ``dedupe_key``, ever."""
    await enqueue(
        session,
        ANALYTICS_CAPTURE,
        {
            "uuid": str(uuid.uuid7()),
            "event": name,
            "distinct_id": str(distinct_id),
            "properties": dict(properties),
            "timestamp": clock.now().isoformat(),
        },
        clock=clock,
        dedupe_key=f"{ANALYTICS_CAPTURE}:{dedupe_key}",
    )


def capture_handler(analytics: Analytics) -> JobHandler:
    async def handle(_context: JobContext, payload: JobPayload) -> None:
        properties = payload["properties"]
        await analytics.capture(
            AnalyticsEvent(
                uuid=str(payload["uuid"]),
                name=str(payload["event"]),
                distinct_id=str(payload["distinct_id"]),
                properties=properties if isinstance(properties, Mapping) else {},
                timestamp=datetime.fromisoformat(str(payload["timestamp"])),
            )
        )

    return handle
