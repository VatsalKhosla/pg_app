"""Media use cases (ARCHITECTURE §13, ADR 0022).

1. **Start:** someone allowed asks to upload a file of a purpose, type and size. They get a
   presigned form that posts the file straight to the private bucket, where storage itself
   refuses another type or a larger file.
2. **Finish:** the uploader says the upload is done. The service checks that storage has the
   file, outside any transaction, and queues it for the worker.
3. **Process** (the worker):
   - check the file's real type against what was claimed;
   - strip its metadata and make the variants (processing.py);
   - store them, in the public bucket for listing media or the private one otherwise;
   - mark the asset ready, or rejected with the reason.

   A second job then deletes the original, which still carries the metadata. It runs only once
   the result has committed, so a failed attempt can try again.
4. **View:** the asset and its files' addresses. Public files are served through the CDN;
   private ones through links signed for five minutes.
"""

import asyncio
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from app.core import audit
from app.core.errors import ForbiddenError, NotFoundError
from app.core.outbox import enqueue
from app.modules.media.domain.assets import (
    RULES,
    SIGNED_URL_TTL,
    UPLOAD_TTL,
    AssetStatus,
    Moderation,
    Purpose,
    Visibility,
    upload_problems,
)
from app.modules.media.domain.sniff import HEAD_BYTES, sniff
from app.modules.media.errors import MediaNotAllowedError, MediaNotUploadedError
from app.modules.media.models import MediaAsset
from app.modules.media.policies import can_finish, can_upload, can_view, is_verified_capture
from app.modules.media.processing import (
    Processed,
    UnprocessableError,
    process_document,
    process_photo,
    process_video,
)
from app.modules.media.repository import MediaRepository

if TYPE_CHECKING:
    import uuid
    from collections.abc import Collection
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.config import Settings
    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.modules.media.ports import ObjectStorage, PresignedUpload

PROCESS: Final = "media.process"
DISCARD_UPLOAD: Final = "media.discard_upload"
# Public files never change (a new upload gets a new id), so caches may keep them for a year.
PUBLIC_CACHE: Final = "public, max-age=31536000, immutable"


@dataclass(frozen=True, slots=True)
class Buckets:
    private: str
    public: str
    # Where the public bucket is read from: the CDN when deployed.
    public_base_url: str

    @classmethod
    def from_settings(cls, settings: Settings) -> Buckets:
        return cls(
            private=settings.media_private_bucket,
            public=settings.media_public_bucket,
            public_base_url=settings.media_public_base_url,
        )


@dataclass(frozen=True, slots=True)
class StartedUpload:
    asset: MediaAsset
    upload: PresignedUpload
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class RenditionView:
    name: str
    content_type: str
    url: str
    width: int | None
    height: int | None
    bytes: int


def upload_key(public_id: uuid.UUID) -> str:
    return f"uploads/{public_id}"


def _rendition_key(asset: MediaAsset, name: str, extension: str) -> str:
    folder = "media" if asset.visibility == Visibility.PUBLIC else "files"
    return f"{folder}/{asset.public_id}/{name}.{extension}"


class MediaService:
    def __init__(
        self, db: AsyncSession, clock: Clock, *, storage: ObjectStorage, buckets: Buckets
    ) -> None:
        self._db = db
        self._clock = clock
        self._storage = storage
        self._buckets = buckets
        self._media = MediaRepository(db)

    async def start_upload(
        self, actor: Actor, *, purpose: Purpose, content_type: str, byte_size: int
    ) -> StartedUpload:
        if not can_upload(actor, purpose):
            raise ForbiddenError
        if problems := upload_problems(purpose, content_type, byte_size):
            raise MediaNotAllowedError(problems)
        rules = RULES[purpose]
        async with self._db.begin():
            asset = await self._media.add(
                MediaAsset(
                    purpose=purpose,
                    visibility=rules.visibility,
                    status=AssetStatus.AWAITING_UPLOAD,
                    # Staff uploads need no review; owners' and students' will (later steps).
                    moderation=Moderation.APPROVED if actor.is_staff else Moderation.PENDING,
                    content_type=content_type,
                    renditions=[],
                    verified_capture=is_verified_capture(actor, purpose),
                    uploaded_by=actor.user_id,
                )
            )
        upload = self._storage.presign_upload(
            self._buckets.private,
            upload_key(asset.public_id),
            content_type=content_type,
            max_bytes=rules.max_bytes,
            expires_in=UPLOAD_TTL,
        )
        return StartedUpload(asset, upload, self._clock.now() + UPLOAD_TTL)

    async def finish_upload(self, actor: Actor, media_id: uuid.UUID) -> MediaAsset:
        async with self._db.begin():
            asset = await self._media.get(media_id)
        if asset is None or not can_finish(actor, uploaded_by=asset.uploaded_by):
            raise NotFoundError
        if asset.status != AssetStatus.AWAITING_UPLOAD:
            return asset  # already finished: saying so again changes nothing
        # Asked of storage before any row is locked (backend rules).
        size = await self._storage.size(self._buckets.private, upload_key(asset.public_id))
        if size is None:
            raise MediaNotUploadedError
        async with self._db.begin():
            asset = await self._media.get(media_id, lock=True)
            if asset is None:
                raise NotFoundError
            if asset.status == AssetStatus.AWAITING_UPLOAD:
                asset.byte_size = size
                asset.status = AssetStatus.PROCESSING
                await enqueue(
                    self._db,
                    PROCESS,
                    {"media_id": str(asset.public_id)},
                    clock=self._clock,
                    dedupe_key=f"{PROCESS}:{asset.public_id}",
                )
                await audit.record(
                    self._db,
                    clock=self._clock,
                    actor=audit.Actor("staff" if actor.is_staff else "user", actor.user_id),
                    action="media.uploaded",
                    entity_type="media",
                    entity_id=str(asset.public_id),
                    details={"purpose": asset.purpose, "byte_size": size},
                )
        return asset

    async def view(
        self, actor: Actor, media_id: uuid.UUID
    ) -> tuple[MediaAsset, list[RenditionView]]:
        async with self._db.begin():
            asset = await self._media.get(media_id)
        if asset is None or not can_view(actor, uploaded_by=asset.uploaded_by):
            raise NotFoundError
        return asset, [self._rendition(asset, stored) for stored in asset.renditions]

    def _rendition(self, asset: MediaAsset, stored: dict[str, object]) -> RenditionView:
        key = str(stored["key"])
        if asset.visibility == Visibility.PUBLIC:
            url = f"{self._buckets.public_base_url}/{key}"
        else:
            url = self._storage.presign_download(
                self._buckets.private,
                key,
                expires_in=SIGNED_URL_TTL,
                filename=key.rsplit("/", 1)[-1],
            )
        return RenditionView(
            name=str(stored["name"]),
            content_type=str(stored["content_type"]),
            url=url,
            width=_maybe_int(stored.get("width")),
            height=_maybe_int(stored.get("height")),
            bytes=int(str(stored["bytes"])),
        )


def _maybe_int(value: object) -> int | None:
    return None if value is None else int(str(value))


def _process(asset: MediaAsset, original: Path, work: Path, now: datetime) -> Processed:
    """The CPU-heavy part, run in a thread."""
    rules = RULES[Purpose(asset.purpose)]
    if original.stat().st_size > rules.max_bytes:
        msg = "the file is larger than this upload allows"
        raise UnprocessableError(msg)
    with original.open("rb") as file:
        found = sniff(file.read(HEAD_BYTES))
    if found != asset.content_type:
        msg = f"the file isn't the {asset.content_type} it was said to be"
        raise UnprocessableError(msg)
    match Purpose(asset.purpose):
        case Purpose.LISTING_PHOTO | Purpose.VERIFICATION_PHOTO | Purpose.DISPUTE_PHOTO:
            return process_photo(original.read_bytes(), asset.content_type, now=now)
        case Purpose.LISTING_VIDEO:
            return process_video(original, work)
        case Purpose.DOCUMENT:
            return process_document(original.read_bytes(), asset.content_type)


async def process_upload(
    db: AsyncSession,
    clock: Clock,
    *,
    storage: ObjectStorage,
    buckets: Buckets,
    media_id: uuid.UUID,
) -> None:
    """The worker's job: make an upload safe to show, in the job's transaction. No row is
    locked while storage is used; the asset changes at the end."""
    media = MediaRepository(db)
    asset = await media.get(media_id)
    if asset is None or asset.status != AssetStatus.PROCESSING:
        return  # done already, or never finished: nothing to do
    public = asset.visibility == Visibility.PUBLIC
    with tempfile.TemporaryDirectory(prefix="media-") as directory:
        work = Path(directory)
        original = work / "original"
        await storage.download(buckets.private, upload_key(asset.public_id), original)
        try:
            processed = await asyncio.to_thread(_process, asset, original, work, clock.now())
        except UnprocessableError as error:
            asset.status = AssetStatus.REJECTED
            asset.rejection_reason = str(error)
        else:
            stored = []
            for rendition in processed.renditions:
                key = _rendition_key(asset, rendition.name, rendition.extension)
                await storage.upload(
                    buckets.public if public else buckets.private,
                    key,
                    rendition.body,
                    content_type=rendition.content_type,
                    cache_control=PUBLIC_CACHE if public else None,
                )
                size = (
                    len(rendition.body)
                    if isinstance(rendition.body, bytes)
                    else rendition.body.stat().st_size
                )
                stored.append(
                    {
                        "name": rendition.name,
                        "content_type": rendition.content_type,
                        "key": key,
                        "width": rendition.width,
                        "height": rendition.height,
                        "bytes": size,
                    }
                )
            asset.status = AssetStatus.READY
            asset.renditions = stored
            asset.width, asset.height = processed.width, processed.height
            asset.duration_ms = processed.duration_ms
            asset.captured_at = processed.captured_at
    asset.processed_at = clock.now()
    await enqueue(
        db,
        DISCARD_UPLOAD,
        {"media_id": str(asset.public_id)},
        clock=clock,
        dedupe_key=f"{DISCARD_UPLOAD}:{asset.public_id}",
    )
    await db.flush()


async def discard_upload(storage: ObjectStorage, buckets: Buckets, media_id: uuid.UUID) -> None:
    """Delete an original once its asset is processed: it still has its metadata."""
    await storage.delete(buckets.private, upload_key(media_id))


@dataclass(frozen=True, slots=True)
class MediaRef:
    """A file, as another module shows or attaches it."""

    id: int
    public_id: uuid.UUID
    purpose: Purpose
    status: AssetStatus
    # Only an approved file may be shown to the public.
    moderation: Moderation
    content_type: str
    verified_capture: bool
    captured_at: datetime | None
    uploaded_by: int | None
    renditions: tuple[RenditionView, ...]


class MediaLookup:
    """Media reads for other modules, inside the caller's transaction (it starts none): what the
    catalog attaches to a listing, or to a verification report. Public media come with their
    addresses; private ones only when the caller passes ``storage``, with links signed for five
    minutes, and only for a caller that has already decided the reader may see them."""

    def __init__(
        self, db: AsyncSession, buckets: Buckets, *, storage: ObjectStorage | None = None
    ) -> None:
        self._media = MediaRepository(db)
        self._buckets = buckets
        self._storage = storage

    def _url(self, asset: MediaAsset, key: str) -> str | None:
        if asset.visibility == Visibility.PUBLIC:
            return f"{self._buckets.public_base_url}/{key}"
        if self._storage is None:
            return None
        return self._storage.presign_download(
            self._buckets.private, key, expires_in=SIGNED_URL_TTL, filename=key.rsplit("/", 1)[-1]
        )

    def _ref(self, asset: MediaAsset) -> MediaRef:
        renditions = []
        for stored in asset.renditions:
            url = self._url(asset, str(stored["key"]))
            if url is not None:
                renditions.append(
                    RenditionView(
                        name=str(stored["name"]),
                        content_type=str(stored["content_type"]),
                        url=url,
                        width=_maybe_int(stored.get("width")),
                        height=_maybe_int(stored.get("height")),
                        bytes=int(str(stored["bytes"])),
                    )
                )
        return MediaRef(
            id=asset.id,
            public_id=asset.public_id,
            purpose=Purpose(asset.purpose),
            status=AssetStatus(asset.status),
            moderation=Moderation(asset.moderation),
            content_type=asset.content_type,
            verified_capture=asset.verified_capture,
            captured_at=asset.captured_at,
            uploaded_by=asset.uploaded_by,
            renditions=tuple(renditions),
        )

    async def by_public_id(self, public_ids: Collection[uuid.UUID]) -> dict[uuid.UUID, MediaRef]:
        return {asset.public_id: self._ref(asset) for asset in await self._media.many(public_ids)}

    async def by_id(self, ids: Collection[int]) -> dict[int, MediaRef]:
        return {asset.id: self._ref(asset) for asset in await self._media.by_ids(ids)}
