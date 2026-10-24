"""Media tables (ARCHITECTURE §13, ADR 0022): one row per upload, holding what became of it."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Model
from app.core.ids import new_public_id
from app.modules.media.domain.assets import AssetStatus, Moderation, Purpose, Visibility

if TYPE_CHECKING:
    from collections.abc import Iterable
    from enum import StrEnum


def _one_of(column: str, values: Iterable[StrEnum]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


class MediaAsset(Model):
    __tablename__ = "media_assets"

    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=new_public_id)
    purpose: Mapped[str] = mapped_column(Text)
    visibility: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    moderation: Mapped[str] = mapped_column(Text)
    # As the uploader said; the worker checks the file's signature against it.
    content_type: Mapped[str] = mapped_column(Text)
    byte_size: Mapped[int | None] = mapped_column(BigInteger)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    # What the worker stored: name, content_type, key, width, height and bytes of each file.
    renditions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    # Taken by a field agent, shown as "Verified photo · <date>".
    verified_capture: Mapped[bool] = mapped_column(Boolean)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    uploaded_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(_one_of("purpose", Purpose), name="purpose"),
        CheckConstraint(_one_of("visibility", Visibility), name="visibility"),
        CheckConstraint(_one_of("status", AssetStatus), name="status"),
        CheckConstraint(_one_of("moderation", Moderation), name="moderation"),
        CheckConstraint("byte_size > 0", name="byte_size"),
        CheckConstraint("width > 0 AND height > 0", name="dimensions"),
        CheckConstraint("duration_ms >= 0", name="duration"),
        CheckConstraint("jsonb_typeof(renditions) = 'array'", name="renditions"),
        Index("ix_media_assets_uploaded_by", "uploaded_by"),
    )
