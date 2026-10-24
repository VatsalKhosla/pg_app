"""Media routes (ARCHITECTURE §13, §15): start an upload, say it's done, and see what became of
it. The file itself goes straight to storage, never through the API."""

import uuid

from fastapi import APIRouter, Request, status

from app.core.clock import ClockDep
from app.core.current_actor import CurrentActor
from app.core.db import DbSession
from app.modules.media.domain.assets import AssetStatus, Moderation, Purpose
from app.modules.media.models import MediaAsset
from app.modules.media.schemas import (
    MediaInfo,
    RenditionInfo,
    UploadForm,
    UploadRequest,
    UploadStarted,
)
from app.modules.media.service import MediaService, RenditionView

router = APIRouter(prefix="/v1", tags=["media"])


def _service(request: Request, db: DbSession, clock: ClockDep) -> MediaService:
    return MediaService(
        db, clock, storage=request.app.state.storage, buckets=request.app.state.media_buckets
    )


def _info(asset: MediaAsset, renditions: list[RenditionView]) -> MediaInfo:
    return MediaInfo(
        id=asset.public_id,
        purpose=Purpose(asset.purpose),
        status=AssetStatus(asset.status),
        moderation=Moderation(asset.moderation),
        content_type=asset.content_type,
        byte_size=asset.byte_size,
        width=asset.width,
        height=asset.height,
        duration_ms=asset.duration_ms,
        verified_capture=asset.verified_capture,
        captured_at=asset.captured_at,
        rejection_reason=asset.rejection_reason,
        renditions=[
            RenditionInfo(
                name=view.name,
                content_type=view.content_type,
                url=view.url,
                width=view.width,
                height=view.height,
                bytes=view.bytes,
            )
            for view in renditions
        ],
    )


@router.post("/media", status_code=status.HTTP_201_CREATED, summary="Start an upload")
async def start_upload(
    body: UploadRequest, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> UploadStarted:
    """Staff, in a staff session. The answer has a form to post the file to, straight to
    storage, within 15 minutes; then say it's done."""
    started = await _service(request, db, clock).start_upload(
        actor, purpose=body.purpose, content_type=body.content_type, byte_size=body.byte_size
    )
    return UploadStarted(
        media=_info(started.asset, []),
        upload=UploadForm(
            url=started.upload.url, fields=started.upload.fields, expires_at=started.expires_at
        ),
    )


@router.post(
    "/media/{media_id}/uploaded",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Say an upload is done",
)
async def finish_upload(
    media_id: uuid.UUID, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> MediaInfo:
    """The uploader only. The file is checked and its variants made in the background: look
    at the media until it is ready or rejected. Saying it again changes nothing."""
    asset = await _service(request, db, clock).finish_upload(actor, media_id)
    return _info(asset, [])


@router.get("/media/{media_id}", summary="A file and its variants")
async def media(
    media_id: uuid.UUID, request: Request, actor: CurrentActor, db: DbSession, clock: ClockDep
) -> MediaInfo:
    """The uploader, or ops and admins in a staff session (404 for anyone else)."""
    asset, renditions = await _service(request, db, clock).view(actor, media_id)
    return _info(asset, renditions)
