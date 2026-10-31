"""What can be uploaded, by whom, and what becomes of it (ARCHITECTURE §13).

Files go straight from the browser to storage, through a presigned upload that checks the
content type and the size. The worker then checks the file's real type, strips its metadata
(EXIF, GPS and a video's location), makes the variants, and marks the asset ready, or rejected
with a reason. Only processed variants are ever served: listing media from the public bucket and
the CDN, everything else through short-lived signed URLs.
"""

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from typing import Final

MIB: Final = 1024 * 1024


class Purpose(StrEnum):
    LISTING_PHOTO = "listing_photo"
    LISTING_VIDEO = "listing_video"
    # A private file: a licence, an agreement scan, a KYC document.
    DOCUMENT = "document"
    # A field agent's evidence from a verification visit (ADR 0024): kept private, like a
    # document, but prepared as a photo.
    VERIFICATION_PHOTO = "verification_photo"
    # A student's evidence that their room isn't as shown (ADR 0051): private too.
    DISPUTE_PHOTO = "dispute_photo"


class Visibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"


class AssetStatus(StrEnum):
    # Waiting for the browser to upload it.
    AWAITING_UPLOAD = "awaiting_upload"
    PROCESSING = "processing"
    READY = "ready"
    REJECTED = "rejected"


class Moderation(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


JPEG: Final = "image/jpeg"
PNG: Final = "image/png"
WEBP: Final = "image/webp"
MP4: Final = "video/mp4"
PDF: Final = "application/pdf"


@dataclass(frozen=True, slots=True)
class Rules:
    content_types: frozenset[str]
    max_bytes: int
    visibility: Visibility


# HEIC is left out: browsers hand iPhone photos over as JPEG when a page doesn't accept HEIC, and
# decoding it would need a codec with licensing questions (ADR 0022). SVG is never accepted.
RULES: Final = {
    Purpose.LISTING_PHOTO: Rules(frozenset({JPEG, PNG, WEBP}), 15 * MIB, Visibility.PUBLIC),
    Purpose.LISTING_VIDEO: Rules(frozenset({MP4}), 200 * MIB, Visibility.PUBLIC),
    Purpose.DOCUMENT: Rules(frozenset({PDF, JPEG, PNG}), 10 * MIB, Visibility.PRIVATE),
    Purpose.VERIFICATION_PHOTO: Rules(frozenset({JPEG, PNG, WEBP}), 15 * MIB, Visibility.PRIVATE),
    Purpose.DISPUTE_PHOTO: Rules(frozenset({JPEG, PNG, WEBP}), 15 * MIB, Visibility.PRIVATE),
}

# How long a presigned upload stays usable, and a signed link to a private file.
UPLOAD_TTL: Final = timedelta(minutes=15)
SIGNED_URL_TTL: Final = timedelta(minutes=5)
# Videos are tours, not films; transcoding can come later.
MAX_VIDEO_SECONDS: Final = 180
# Larger images are refused before decoding, so a small file can't expand into a huge one.
MAX_PIXELS: Final = 50_000_000

_NEXT: Final = {
    AssetStatus.AWAITING_UPLOAD: frozenset({AssetStatus.PROCESSING}),
    AssetStatus.PROCESSING: frozenset({AssetStatus.READY, AssetStatus.REJECTED}),
    AssetStatus.READY: frozenset[AssetStatus](),
    AssetStatus.REJECTED: frozenset[AssetStatus](),
}


def can_move(current: AssetStatus, target: AssetStatus) -> bool:
    return target in _NEXT[current]


def upload_problems(purpose: Purpose, content_type: str, byte_size: int) -> list[str]:
    """Why an upload can't start; empty when it can."""
    rules = RULES[purpose]
    problems = []
    if content_type not in rules.content_types:
        allowed = ", ".join(sorted(rules.content_types))
        problems.append(f"a {purpose} must be one of: {allowed}")
    if not 0 < byte_size <= rules.max_bytes:
        problems.append(f"a {purpose} must be at most {rules.max_bytes // MIB} MB")
    return problems


# The image variants every photo, and every video's poster, gets: the longest edge in pixels.
VARIANT_EDGES: Final = {"thumb": 160, "card": 480, "gallery": 1080, "full": 2048}


def variant_size(width: int, height: int, longest_edge: int) -> tuple[int, int]:
    """The size that fits ``longest_edge``, keeping the shape and never enlarging."""
    scale = min(1.0, longest_edge / max(width, height))
    return max(1, round(width * scale)), max(1, round(height * scale))
