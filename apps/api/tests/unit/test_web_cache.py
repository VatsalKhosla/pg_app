"""Telling the web app its pages are out of date (step 3.6, ADR 0032), without a web app: the
signed request it gets, what happens when it refuses, and when nothing is sent at all."""

import asyncio
import hashlib
import hmac
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.core.clock import FrozenClock
from app.core.web_cache import (
    NoWebCache,
    SignedWebCache,
    WebCacheError,
    ask_to_revalidate,
    listing_tag,
    signature,
)
from app.worker import web_cache

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

SECRET = "a-revalidation-secret-of-32-chars!!"
NOW = datetime(2027, 7, 14, 10, 0, tzinfo=UTC)


def _cache(handler: httpx.MockTransport) -> SignedWebCache:
    return SignedWebCache(
        httpx.AsyncClient(transport=handler),
        site_url="https://www.example.in",
        secret=SecretStr(SECRET),
    )


def test_the_web_app_gets_the_tags_signed_with_the_time() -> None:
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"revalidated": True})

    asyncio.run(
        _cache(httpx.MockTransport(answer)).revalidate(
            [listing_tag("asha-pg-kamla-nagar"), "listings"], now=NOW
        )
    )

    [request] = seen
    assert (request.method, str(request.url)) == ("POST", "https://www.example.in/api/revalidate")
    assert json.loads(request.content) == {"tags": ["listing:asha-pg-kamla-nagar", "listings"]}
    timestamp = request.headers["X-Revalidate-Timestamp"]
    assert timestamp == str(int(NOW.timestamp()))
    # The HMAC of "<time>.<body>", as the web app works it out (src/lib/security/revalidation.ts).
    expected = hmac.new(
        SECRET.encode(), f"{timestamp}.".encode() + request.content, hashlib.sha256
    ).hexdigest()
    assert request.headers["X-Revalidate-Signature"] == expected
    assert signature(SECRET, timestamp, request.content) == expected


@pytest.mark.parametrize("status", [401, 404, 500, 503])
def test_anything_but_200_is_an_error_so_the_outbox_tries_again(status: int) -> None:
    cache = _cache(httpx.MockTransport(lambda _: httpx.Response(status)))

    with pytest.raises(WebCacheError, match=str(status)):
        asyncio.run(cache.revalidate(["listings"], now=NOW))


def test_without_a_secret_nothing_is_sent(make_settings: Callable[..., Settings]) -> None:
    def refuse(_: httpx.Request) -> httpx.Response:  # pragma: no cover - never called
        raise AssertionError("nothing should be sent")

    http = httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    settings = make_settings(revalidate_secret=None)

    cache = web_cache(settings, http)

    assert isinstance(cache, NoWebCache)
    asyncio.run(cache.revalidate(["listings"], now=NOW))
    signed = web_cache(settings.model_copy(update={"revalidate_secret": SecretStr(SECRET)}), http)
    assert isinstance(signed, SignedWebCache)


@pytest.mark.parametrize("tag", ["listing:Not A Slug", "everything", "listing:", "reference"])
def test_only_tags_the_web_app_knows_are_asked_for(tag: str) -> None:
    # Refused before the database is touched, so no session is needed.
    session = cast("AsyncSession", object())

    with pytest.raises(ValueError, match="not tags the web app knows"):
        asyncio.run(ask_to_revalidate(session, FrozenClock(NOW), ["listings", tag]))
