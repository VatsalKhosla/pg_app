"""Telling the web app that pages it keeps are out of date (step 3.6, ADR 0032).

The web app keeps the public data its pages are made from (a listing, search's first page, the
landing pages' lists) in Next's data cache, each entry tagged: ``listing:<slug>`` for one
listing's page, ``listings`` for anything that lists them. When a listing changes, a job posts
the tags to the web app's ``/api/revalidate``, signed with a secret both share, and the next
visit to those pages fetches fresh data. Without the secret (local development, tests) nothing
is sent, and the web app's caches expire on their own within a minute.

The signature is an HMAC-SHA256 of ``<unix time>.<body>``, in hex, sent with the time; the web
app refuses a request more than five minutes old, so a captured one soon stops working.
"""

import hashlib
import hmac
import json
import re
from typing import TYPE_CHECKING, Final, Protocol

import structlog

from app.core.outbox import enqueue

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    import httpx
    from pydantic import SecretStr
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.clock import Clock
    from app.core.outbox import JobContext, JobHandler, JobPayload

REVALIDATE: Final = "web.revalidate"
# The tags the web app knows: one listing's, everything that lists them, and the pages that
# state the fee and booking policies (ADR 0036).
LISTINGS_TAG: Final = "listings"
POLICIES_TAG: Final = "policies"
_TAG: Final = re.compile(r"^(listings|policies|listing:[a-z0-9]+(-[a-z0-9]+)*)$")
_PATH: Final = "/api/revalidate"

logger = structlog.stdlib.get_logger(__name__)


def listing_tag(slug: str) -> str:
    return f"listing:{slug}"


class WebCacheError(Exception):
    """The web app didn't take the request; the outbox tries the job again later."""


class WebCache(Protocol):
    async def revalidate(self, tags: Sequence[str], *, now: datetime) -> None:
        """Mark the web app's data under these tags as stale."""


class NoWebCache:
    """No secret, so nothing to tell: the web app's caches expire on their own."""

    async def revalidate(self, tags: Sequence[str], *, now: datetime) -> None:
        logger.debug("web revalidation off", tags=list(tags))


def signature(secret: str, timestamp: str, body: bytes) -> str:
    """The request's HMAC, as the web app works it out too."""
    return hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


class SignedWebCache:
    """The web app's ``/api/revalidate``, signed with the shared secret. Any answer but 200 is
    an error, so the outbox retries it with backoff."""

    def __init__(self, http: httpx.AsyncClient, *, site_url: str, secret: SecretStr) -> None:
        self._http = http
        self._url = f"{site_url}{_PATH}"
        self._secret = secret

    async def revalidate(self, tags: Sequence[str], *, now: datetime) -> None:
        body = json.dumps({"tags": list(tags)}, separators=(",", ":")).encode()
        timestamp = str(int(now.timestamp()))
        response = await self._http.post(
            self._url,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Revalidate-Timestamp": timestamp,
                "X-Revalidate-Signature": signature(
                    self._secret.get_secret_value(), timestamp, body
                ),
            },
        )
        if response.status_code != 200:
            msg = f"the web app answered {response.status_code} to revalidating {list(tags)}"
            raise WebCacheError(msg)
        logger.info("web revalidated", tags=list(tags))


async def ask_to_revalidate(db: AsyncSession, clock: Clock, tags: Sequence[str]) -> None:
    """A job, in the caller's transaction, to revalidate ``tags`` once it commits."""
    if invalid := [tag for tag in tags if not _TAG.fullmatch(tag)]:
        msg = f"not tags the web app knows: {invalid}"
        raise ValueError(msg)
    await enqueue(db, REVALIDATE, {"tags": list(tags)}, clock=clock)


def revalidate_handler(cache: WebCache) -> JobHandler:
    async def handle(context: JobContext, payload: JobPayload) -> None:
        await cache.revalidate([str(tag) for tag in payload["tags"]], now=context.clock.now())

    return handle
