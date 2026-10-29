"""Server-side analytics (step 3.9, ADR 0035), without a network: the batch PostHog is sent, and
what a refusal does."""

import asyncio
import json
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import SecretStr

from app.core.analytics import (
    AnalyticsError,
    AnalyticsEvent,
    PostHogAnalytics,
    capture_handler,
)

EVENT = AnalyticsEvent(
    uuid="0192f0a4-0000-7000-8000-000000000001",
    name="visit_completed",
    distinct_id="0192f0a4-0000-7000-8000-0000000000aa",
    properties={"outcome": "interested"},
    timestamp=datetime(2027, 7, 16, 5, 40, tzinfo=UTC),
)


def _posthog(status: int, seen: list[httpx.Request]) -> PostHogAnalytics:
    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json={"status": "Ok"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(answer))
    return PostHogAnalytics(
        http, host="https://eu.i.posthog.com/", project_key=SecretStr("phc_fictional")
    )


def test_an_event_goes_to_the_batch_endpoint_personless_and_without_geoip() -> None:
    seen: list[httpx.Request] = []

    asyncio.run(_posthog(200, seen).capture(EVENT))

    [request] = seen
    assert (request.method, str(request.url)) == ("POST", "https://eu.i.posthog.com/batch/")
    assert json.loads(request.content) == {
        "api_key": "phc_fictional",
        "batch": [
            {
                "uuid": EVENT.uuid,
                "event": "visit_completed",
                "distinct_id": EVENT.distinct_id,
                "timestamp": "2027-07-16T05:40:00+00:00",
                "properties": {
                    "outcome": "interested",
                    "$process_person_profile": False,
                    "$geoip_disable": True,
                    "$lib": "api",
                },
            }
        ],
    }


def test_a_refusal_raises_so_the_job_is_tried_again() -> None:
    with pytest.raises(AnalyticsError):
        asyncio.run(_posthog(503, []).capture(EVENT))


def test_the_job_sends_what_was_queued() -> None:
    captured: list[AnalyticsEvent] = []

    class Recorder:
        async def capture(self, event: AnalyticsEvent) -> None:
            captured.append(event)

    handle = capture_handler(Recorder())
    asyncio.run(
        handle(
            None,  # type: ignore[arg-type]  # the handler doesn't use the job's context
            {
                "uuid": EVENT.uuid,
                "event": EVENT.name,
                "distinct_id": EVENT.distinct_id,
                "properties": {"outcome": "interested"},
                "timestamp": EVENT.timestamp.isoformat(),
            },
        )
    )

    assert captured == [EVENT]
