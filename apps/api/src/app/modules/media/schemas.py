"""Media requests and responses (ARCHITECTURE §15)."""

import uuid
from datetime import datetime

from pydantic import Field

from app.core.schemas import ApiModel
from app.modules.media.domain.assets import AssetStatus, Moderation, Purpose


class UploadRequest(ApiModel):
    purpose: Purpose
    content_type: str = Field(min_length=1, max_length=100)
    # What the file weighs, so a file too large is refused before it is sent.
    byte_size: int = Field(gt=0)


class UploadForm(ApiModel):
    """Post the file here as multipart/form-data: every field, then the file as ``file``."""

    url: str
    fields: dict[str, str]
    expires_at: datetime


class RenditionInfo(ApiModel):
    # thumb, card, gallery or full; video for a video; original for a PDF.
    name: str
    content_type: str
    # Public files: their CDN address. Private ones: a link signed for five minutes.
    url: str
    width: int | None
    height: int | None
    bytes: int


class MediaInfo(ApiModel):
    id: uuid.UUID
    purpose: Purpose
    status: AssetStatus
    moderation: Moderation
    content_type: str
    byte_size: int | None
    width: int | None
    height: int | None
    duration_ms: int | None
    verified_capture: bool
    captured_at: datetime | None
    # Why the worker refused the file, when it did.
    rejection_reason: str | None
    renditions: list[RenditionInfo]


class UploadStarted(ApiModel):
    media: MediaInfo
    upload: UploadForm
