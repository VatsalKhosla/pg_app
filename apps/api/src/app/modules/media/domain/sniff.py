"""What a file really is, from its first bytes: browsers and people can say anything about a
file's type, so the worker checks the signature itself."""

from typing import Final

from app.modules.media.domain.assets import JPEG, MP4, PDF, PNG, WEBP

# Enough of the start of a file for every signature below.
HEAD_BYTES: Final = 16
# MP4 brands phones and cameras write (ISO base media; QuickTime "qt  " too).
_MP4_BRANDS: Final = frozenset(
    {b"isom", b"iso2", b"iso4", b"iso5", b"iso6", b"mp41", b"mp42", b"avc1", b"M4V ", b"qt  "}
)


def sniff(head: bytes) -> str | None:
    """The content type the bytes are, among those uploads may be, or None."""
    if head.startswith(b"\xff\xd8\xff"):
        return JPEG
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return WEBP
    if head[4:8] == b"ftyp" and head[8:12] in _MP4_BRANDS:
        return MP4
    if head.startswith(b"%PDF-"):
        return PDF
    return None
