"""Uploads end to end against real object storage (SeaweedFS, as `make dev` runs it): from the
browser straight to storage, through the worker, and out as variants (step 2.3).

Done when an uploaded phone photo comes out with no GPS EXIF in any variant, and a private
document needs a signed URL.
"""

import asyncio
import io
import secrets
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from PIL import Image

from app.config import Settings
from app.core.actor import Role
from app.core.clock import FrozenClock
from app.core.cookies import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from app.core.csrf import issue_csrf_token
from app.core.outbox import OutboxWorker
from app.core.web_cache import NoWebCache
from app.jobs import build_registry
from app.main import create_app
from app.modules.identity.domain.sessions import SessionKind
from app.modules.identity.repository import UserRepository
from app.modules.identity.service import SessionService
from app.modules.media.adapters.s3 import S3Storage
from app.modules.media.service import upload_key
from tests.conftest import TEST_SECRET_KEY
from tests.media_samples import assert_clean, phone_photo, phone_video

pytestmark = pytest.mark.integration

RUN = secrets.token_hex(4)
PRIVATE = f"private-{RUN}"
PUBLIC = f"media-{RUN}"

type Scenario = Callable[["Uploader"], Awaitable[Any]]


class Uploader:
    """A staff member of one role, with a session, uploading as the web app would."""

    def __init__(self, app: FastAPI, client: httpx.AsyncClient, token: str) -> None:
        self.app = app
        self.client = client
        self._token = token

    def headers(self) -> dict[str, str]:
        csrf = issue_csrf_token(TEST_SECRET_KEY.encode(), self._token)
        return {
            CSRF_HEADER: csrf,
            "Cookie": f"{SESSION_COOKIE}={self._token}; {CSRF_COOKIE}={csrf}",
        }

    async def start(self, purpose: str, content_type: str, size: int) -> httpx.Response:
        return await self.client.post(
            "/v1/media",
            json={"purpose": purpose, "contentType": content_type, "byteSize": size},
            headers=self.headers(),
        )

    async def finish(self, media_id: str) -> httpx.Response:
        return await self.client.post(f"/v1/media/{media_id}/uploaded", headers=self.headers())

    async def media(self, media_id: str) -> dict[str, Any]:
        response = await self.client.get(f"/v1/media/{media_id}", headers=self.headers())
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body

    async def upload(self, purpose: str, content_type: str, body: bytes) -> dict[str, Any]:
        """Start, post the file to storage, finish, let the worker run, and look again."""
        started = await self.start(purpose, content_type, len(body))
        assert started.status_code == 201, started.text
        form = started.json()["upload"]
        async with httpx.AsyncClient() as browser:
            stored = await browser.post(
                form["url"], data=form["fields"], files={"file": ("upload", body, content_type)}
            )
        assert stored.status_code == 204, stored.text
        media_id = started.json()["media"]["id"]
        assert (await self.finish(media_id)).status_code == 202
        await self.run_worker()
        return await self.media(media_id)

    async def run_worker(self) -> None:
        worker = OutboxWorker(
            sessionmaker=self.app.state.sessionmaker,
            registry=build_registry(
                storage=self.app.state.storage,
                buckets=self.app.state.media_buckets,
                web_cache=NoWebCache(),
            ),
            clock=self.app.state.clock,
            worker_id="test",
            batch_size=50,
        )
        while await worker.run_once():
            pass


@pytest.fixture
def run(
    make_settings: Callable[..., Settings], database_url: str, storage_url: str
) -> Callable[..., Any]:
    def run_scenario(scenario: Scenario, *, role: Role = Role.FIELD_AGENT) -> Any:
        settings = make_settings(
            database_url=database_url,
            s3_endpoint_url=storage_url,
            s3_access_key_id="pg-platform-dev",
            s3_secret_access_key="pg-platform-dev-only",
            media_private_bucket=PRIVATE,
            media_public_bucket=PUBLIC,
            media_public_base_url=f"{storage_url}/{PUBLIC}",
        )
        S3Storage.from_settings(settings).ensure_local_buckets(
            private=PRIVATE, public=PUBLIC, web_origin="http://localhost:3000"
        )
        app = create_app(settings, clock=FrozenClock(datetime(2027, 6, 12, 12, 0, tzinfo=UTC)))

        async def wrapped() -> Any:
            async with app.router.lifespan_context(app):
                phone = f"+91{6_000_000_000 + secrets.randbelow(4_000_000_000)}"
                async with app.state.sessionmaker() as db:
                    async with db.begin():
                        user = await UserRepository(db).add(phone_e164=phone, roles=[role])
                    session = await SessionService(db, app.state.clock).start(
                        user.id, kind=SessionKind.STAFF, ip_address=None, user_agent=None
                    )
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="https://api.test"
                ) as client:
                    return await scenario(Uploader(app, client, session.token))

        return asyncio.run(wrapped())

    return run_scenario


async def _fetch(url: str) -> httpx.Response:
    async with httpx.AsyncClient() as anyone:
        return await anyone.get(url)


async def _original_left(uploader: Uploader, media_id: str) -> int | None:
    storage: S3Storage = uploader.app.state.storage
    return await storage.size(PRIVATE, upload_key(uuid.UUID(media_id)))


def test_a_phone_photo_comes_out_with_no_gps_exif_in_any_variant(run: Callable[..., Any]) -> None:
    async def scenario(uploader: Uploader) -> tuple[dict[str, Any], list[httpx.Response], Any]:
        media = await uploader.upload("listing_photo", "image/jpeg", phone_photo())
        fetched = [await _fetch(rendition["url"]) for rendition in media["renditions"]]
        return media, fetched, await _original_left(uploader, media["id"])

    media, fetched, original = run(scenario)

    assert media["status"] == "ready", media["rejectionReason"]
    assert media["verifiedCapture"] is True
    assert media["capturedAt"] == "2027-06-12T05:00:05Z"
    assert (media["width"], media["height"]) == (900, 1200)
    assert len(media["renditions"]) == 8
    for rendition, response in zip(media["renditions"], fetched, strict=True):
        # Public, as through the CDN, with no metadata left at all.
        assert response.status_code == 200
        assert response.headers["content-type"] == rendition["contentType"]
        assert "immutable" in response.headers["cache-control"]
        assert_clean(response.content)
    # The original, which still had the GPS, is gone.
    assert original is None


def test_a_private_document_needs_a_signed_url(run: Callable[..., Any]) -> None:
    async def scenario(uploader: Uploader) -> tuple[dict[str, Any], int, int, int]:
        media = await uploader.upload("document", "image/png", phone_photo(fmt="PNG"))
        url = media["renditions"][0]["url"]
        unsigned = url.split("?", 1)[0]
        public_path = unsigned.replace(f"/{PRIVATE}/", f"/{PUBLIC}/")
        return (
            media,
            (await _fetch(url)).status_code,
            (await _fetch(unsigned)).status_code,
            (await _fetch(public_path)).status_code,
        )

    media, signed, unsigned, public = run(scenario, role=Role.OPS)

    assert media["status"] == "ready", media["rejectionReason"]
    assert media["verifiedCapture"] is False
    assert "X-Amz-Signature=" in media["renditions"][0]["url"]
    assert signed == 200
    assert unsigned == 403
    assert public in {403, 404}


def test_a_phone_video_loses_its_location_and_gets_a_poster(
    run: Callable[..., Any], tmp_path: Path
) -> None:
    video = phone_video(tmp_path / "tour.mp4").read_bytes()

    async def scenario(uploader: Uploader) -> tuple[dict[str, Any], dict[str, bytes]]:
        media = await uploader.upload("listing_video", "video/mp4", video)
        files = {
            rendition["name"] + rendition["contentType"]: (await _fetch(rendition["url"])).content
            for rendition in media["renditions"]
        }
        return media, files

    media, files = run(scenario)

    assert media["status"] == "ready", media["rejectionReason"]
    assert media["durationMs"] == pytest.approx(2_000, abs=200)
    assert b"loci" in video
    assert b"loci" not in files["videovideo/mp4"]
    for name, body in files.items():
        if name != "videovideo/mp4":
            assert_clean(body)


def test_a_file_that_isnt_what_it_claims_is_rejected_and_its_original_dropped(
    run: Callable[..., Any],
) -> None:
    png = io.BytesIO()
    Image.new("RGB", (40, 30)).save(png, format="PNG")

    async def scenario(uploader: Uploader) -> tuple[dict[str, Any], int | None]:
        # Storage only checks the content type the form names; the worker checks the bytes.
        media = await uploader.upload("listing_photo", "image/jpeg", png.getvalue())
        return media, await _original_left(uploader, media["id"])

    media, original = run(scenario)

    assert media["status"] == "rejected"
    assert "isn't the image/jpeg" in media["rejectionReason"]
    assert media["renditions"] == []
    assert original is None


def test_storage_itself_refuses_another_content_type(run: Callable[..., Any]) -> None:
    async def scenario(uploader: Uploader) -> int:
        started = (await uploader.start("listing_photo", "image/jpeg", 100)).json()["upload"]
        fields = {**started["fields"], "Content-Type": "image/svg+xml"}
        async with httpx.AsyncClient() as browser:
            response = await browser.post(
                started["url"], data=fields, files={"file": ("x.svg", b"<svg/>", "image/svg+xml")}
            )
        return response.status_code

    assert run(scenario) == 403


def test_uploads_are_refused_up_front_and_done_only_when_stored(run: Callable[..., Any]) -> None:
    async def scenario(uploader: Uploader) -> list[tuple[int, str]]:
        svg = await uploader.start("listing_photo", "image/svg+xml", 100)
        huge = await uploader.start("listing_photo", "image/jpeg", 16 * 1024 * 1024)
        started = await uploader.start("listing_photo", "image/jpeg", 100)
        early = await uploader.finish(started.json()["media"]["id"])
        return [(response.status_code, response.json()["code"]) for response in (svg, huge, early)]

    assert run(scenario) == [
        (422, "MEDIA_NOT_ALLOWED"),
        (422, "MEDIA_NOT_ALLOWED"),
        (409, "MEDIA_NOT_UPLOADED"),
    ]
