"""Making an upload safe to show (ARCHITECTURE §13, ADR 0022). This is CPU-heavy, so the worker
runs it in a thread.

- **Photos** are decoded, but only after their pixel count is checked, then turned upright and
  re-encoded as WebP and AVIF at every variant size. No metadata is carried over except the
  colour profile: no EXIF, so no GPS, no camera serial and no XMP.
- **Videos** are remuxed without re-encoding into a new MP4 holding only their video and audio.
  The container and stream metadata (phones write the location there) and any data tracks are
  left behind. A poster frame gets the photo variants.
- **Documents** that are images are re-encoded the same way. PDFs are kept as they are: they are
  only ever downloaded, never shown inline.
"""

import io
import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import av
from PIL import Image, ImageOps, UnidentifiedImageError

from app.modules.media.domain.assets import (
    JPEG,
    MAX_PIXELS,
    MAX_VIDEO_SECONDS,
    MP4,
    PDF,
    PNG,
    VARIANT_EDGES,
    WEBP,
    variant_size,
)
from app.modules.media.domain.capture import taken_at

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path

    from av.container import InputContainer
    from av.video.stream import VideoStream

AVIF: Final = "image/avif"
_PIL_FORMATS: Final = {JPEG: "JPEG", PNG: "PNG", WEBP: "WEBP"}
_EXTENSIONS: Final = {JPEG: "jpg", PNG: "png", WEBP: "webp", AVIF: "avif", MP4: "mp4", PDF: "pdf"}
_ENCODINGS: Final = (
    (WEBP, {"quality": 82, "method": 4}),
    (AVIF, {"quality": 60, "speed": 6}),
)
# EXIF tags: the Exif sub-IFD, DateTimeOriginal and OffsetTimeOriginal in it.
_EXIF_IFD: Final = 0x8769
_TAKEN: Final = 0x9003
_TAKEN_OFFSET: Final = 0x9011
# Where a video's poster is taken from, unless the video is shorter.
POSTER_AT_SECONDS: Final = 1.0


@dataclass(frozen=True, slots=True)
class Rendition:
    """A file to store: a variant of a photo, a video's poster or the cleaned video itself."""

    name: str
    content_type: str
    body: bytes | Path
    width: int | None = None
    height: int | None = None

    @property
    def extension(self) -> str:
        return _EXTENSIONS[self.content_type]


@dataclass(frozen=True, slots=True)
class Processed:
    renditions: tuple[Rendition, ...]
    width: int | None = None
    height: int | None = None
    duration_ms: int | None = None
    captured_at: datetime | None = None


class UnprocessableError(Exception):
    """A file the worker refuses, with the reason the uploader is shown."""


def _open(data: bytes, content_type: str) -> Image.Image:
    with warnings.catch_warnings():
        # Pillow only warns about very large images; here they are refused.
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            # Only the decoders uploads may need: no TIFF, EPS, GIF or PDF parsing, ever.
            image = Image.open(io.BytesIO(data), formats=tuple(_PIL_FORMATS.values()))
        except (Image.DecompressionBombWarning, Image.DecompressionBombError) as error:
            msg = "the image has too many pixels"
            raise UnprocessableError(msg) from error
        except (UnidentifiedImageError, OSError) as error:
            msg = "the file isn't a readable image"
            raise UnprocessableError(msg) from error
    if image.format != _PIL_FORMATS[content_type]:
        msg = "the image isn't the type it claims to be"
        raise UnprocessableError(msg)
    width, height = image.size
    if width * height > MAX_PIXELS:
        msg = "the image has too many pixels"
        raise UnprocessableError(msg)
    return image


def _taken(image: Image.Image, *, before: datetime) -> datetime | None:
    exif = image.getexif().get_ifd(_EXIF_IFD)
    return taken_at(exif.get(_TAKEN), exif.get(_TAKEN_OFFSET), before=before)


def _clean(image: Image.Image) -> tuple[Image.Image, bytes | None]:
    """The pixels, upright, with nothing else: every metadata entry is dropped but the colour
    profile, which is returned to be written into the variants."""
    try:
        upright = ImageOps.exif_transpose(image)
        upright.load()
    except (OSError, ValueError) as error:
        msg = "the file isn't a readable image"
        raise UnprocessableError(msg) from error
    profile = upright.info.get("icc_profile")
    if upright.mode not in {"RGB", "RGBA"}:
        has_alpha = "A" in upright.getbands() or "transparency" in upright.info
        upright = upright.convert("RGBA" if has_alpha else "RGB")
    upright.info.clear()
    return upright, profile if isinstance(profile, bytes) else None


def _encode(
    image: Image.Image, content_type: str, profile: bytes | None, **options: object
) -> bytes:
    buffer = io.BytesIO()
    if profile is not None:
        options["icc_profile"] = profile
    image.save(buffer, format=_EXTENSIONS[content_type].upper().replace("JPG", "JPEG"), **options)
    return buffer.getvalue()


def _variants(image: Image.Image, profile: bytes | None) -> list[Rendition]:
    renditions: list[Rendition] = []
    for name, edge in VARIANT_EDGES.items():
        size = variant_size(image.width, image.height, edge)
        resized = image if size == image.size else image.resize(size, Image.Resampling.LANCZOS)
        renditions.extend(
            Rendition(name, content_type, _encode(resized, content_type, profile, **options), *size)
            for content_type, options in _ENCODINGS
        )
    return renditions


def process_photo(data: bytes, content_type: str, *, now: datetime) -> Processed:
    image = _open(data, content_type)
    taken = _taken(image, before=now)
    upright, profile = _clean(image)
    return Processed(
        tuple(_variants(upright, profile)),
        width=upright.width,
        height=upright.height,
        captured_at=taken,
    )


def process_document(data: bytes, content_type: str) -> Processed:
    if content_type == PDF:
        return Processed((Rendition("original", PDF, data),))
    upright, profile = _clean(_open(data, content_type))
    options: dict[str, object] = {"quality": 90} if content_type == JPEG else {}
    body = _encode(upright, content_type, profile, **options)
    return Processed(
        (Rendition("full", content_type, body, upright.width, upright.height),),
        width=upright.width,
        height=upright.height,
    )


def _video_stream(container: InputContainer) -> VideoStream:
    if not {"mp4", "mov"} & set(container.format.name.split(",")):
        msg = "the file isn't an MP4 video"
        raise UnprocessableError(msg)
    stream = next(iter(container.streams.video), None)
    if stream is None:
        msg = "the video has no picture"
        raise UnprocessableError(msg)
    return stream


def _poster(container: InputContainer, stream: VideoStream, seconds: float) -> Image.Image:
    at = min(POSTER_AT_SECONDS, seconds / 2)
    container.seek(int(at * av.time_base))
    for frame in container.decode(stream):
        # PyAV declares to_image without types.
        image: Image.Image = frame.to_image()  # type: ignore[no-untyped-call]
        # Phones store portrait video sideways, with a rotation to apply when playing.
        if frame.rotation:
            image = image.rotate(frame.rotation, expand=True)
        return image
    msg = "the video has no frame to show"
    raise UnprocessableError(msg)


def _remux(source: Path, target: Path) -> None:
    """Copy the video and audio, and nothing else, into a new MP4 that starts playing before it
    has downloaded (faststart)."""
    with (
        av.open(str(source)) as original,
        av.open(str(target), "w", format="mp4", options={"movflags": "+faststart"}) as clean,
    ):
        kept = {}
        for stream in original.streams:
            if stream.type in {"video", "audio"}:
                copy = clean.add_stream_from_template(stream)
                copy.metadata.clear()
                kept[stream.index] = copy
        for packet in original.demux(*(original.streams[index] for index in kept)):
            if packet.dts is None:
                continue
            packet.stream = kept[packet.stream.index]
            clean.mux(packet)


def process_video(source: Path, work_dir: Path) -> Processed:
    try:
        with av.open(str(source)) as container:
            stream = _video_stream(container)
            seconds = (container.duration or 0) / av.time_base
            if seconds <= 0:
                msg = "the video's length can't be read"
                raise UnprocessableError(msg)
            if seconds > MAX_VIDEO_SECONDS:
                msg = f"the video is longer than {MAX_VIDEO_SECONDS // 60} minutes"
                raise UnprocessableError(msg)
            width, height = stream.codec_context.width, stream.codec_context.height
            poster = _poster(container, stream, seconds)
        cleaned = work_dir / "clean.mp4"
        _remux(source, cleaned)
    except av.FFmpegError as error:
        msg = "the file isn't a readable video"
        raise UnprocessableError(msg) from error
    upright, profile = _clean(poster)
    return Processed(
        (Rendition("video", MP4, cleaned, width, height), *_variants(upright, profile)),
        width=width,
        height=height,
        duration_ms=round(seconds * 1000),
    )
