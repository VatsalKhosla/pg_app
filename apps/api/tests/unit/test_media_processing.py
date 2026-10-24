"""Making uploads safe to show (step 2.3): no metadata survives in any variant (EXIF, GPS, XMP,
a video's location), photos come out upright, and files that aren't what they claim, or are too
big, are refused. The GPS positions written here are made up."""

import io
from datetime import UTC, datetime
from pathlib import Path

import av
import pytest
from PIL import ExifTags, Image

from app.modules.media import processing
from app.modules.media.domain.assets import JPEG, MP4, PDF, PNG, VARIANT_EDGES, WEBP
from app.modules.media.processing import (
    AVIF,
    Processed,
    UnprocessableError,
    process_document,
    process_photo,
    process_video,
)
from tests.media_samples import GPS, assert_clean, phone_photo, phone_video

NOW = datetime(2027, 6, 12, 12, 0, tzinfo=UTC)


def test_a_phone_photo_comes_out_with_no_metadata_in_any_variant() -> None:
    original = phone_photo()
    assert b"Exif" in original  # the fixture really carries EXIF

    processed = process_photo(original, JPEG, now=NOW)

    names = {(rendition.name, rendition.content_type) for rendition in processed.renditions}
    assert names == {(name, kind) for name in VARIANT_EDGES for kind in (WEBP, AVIF)}
    for rendition in processed.renditions:
        assert isinstance(rendition.body, bytes)
        image = assert_clean(rendition.body)
        assert (image.width, image.height) == (rendition.width, rendition.height)
        assert max(image.size) <= VARIANT_EDGES[rendition.name]


def test_a_photo_comes_out_upright_and_keeps_when_it_was_taken() -> None:
    processed = process_photo(phone_photo(size=(1200, 900)), JPEG, now=NOW)

    # The orientation tag turned the 1200 by 900 pixels to portrait.
    assert (processed.width, processed.height) == (900, 1200)
    # 10:30:05 in India is 05:00:05 UTC.
    assert processed.captured_at == datetime(2027, 6, 12, 5, 0, 5, tzinfo=UTC)


def test_small_photos_are_not_enlarged() -> None:
    processed = process_photo(phone_photo(size=(300, 200)), JPEG, now=NOW)

    full = next(r for r in processed.renditions if r.name == "full" and r.content_type == WEBP)
    assert (full.width, full.height) == (200, 300)


def test_png_and_webp_photos_are_cleaned_too_and_keep_transparency() -> None:
    image = Image.new("RGBA", (400, 300), (0, 0, 0, 0))
    for fmt, kind in (("PNG", PNG), ("WEBP", WEBP)):
        buffer = io.BytesIO()
        exif = Image.Exif()
        exif[ExifTags.IFD.GPSInfo] = GPS
        image.save(buffer, format=fmt, exif=exif)

        processed = process_photo(buffer.getvalue(), kind, now=NOW)

        for rendition in processed.renditions:
            assert isinstance(rendition.body, bytes)
            assert assert_clean(rendition.body).mode == "RGBA"


@pytest.mark.parametrize(
    ("body", "claimed", "reason"),
    [
        (phone_photo(fmt="PNG"), JPEG, "isn't the type it claims"),
        (b"\xff\xd8\xff not really a JPEG", JPEG, "isn't a readable image"),
    ],
)
def test_files_that_arent_what_they_claim_are_refused(
    body: bytes, claimed: str, reason: str
) -> None:
    with pytest.raises(UnprocessableError, match=reason):
        process_photo(body, claimed, now=NOW)


def test_an_image_with_too_many_pixels_is_refused_before_decoding() -> None:
    buffer = io.BytesIO()
    Image.new("1", (7_100, 7_100)).save(buffer, format="PNG")  # 50.4 million pixels

    with pytest.raises(UnprocessableError, match="too many pixels"):
        process_photo(buffer.getvalue(), PNG, now=NOW)


def test_a_document_photo_is_cleaned_and_a_pdf_kept_as_it_is() -> None:
    pdf = b"%PDF-1.7\n%fictional\n"

    photo = process_document(phone_photo(), JPEG)
    kept = process_document(pdf, PDF)

    assert [rendition.name for rendition in photo.renditions] == ["full"]
    body = photo.renditions[0].body
    assert isinstance(body, bytes)
    assert_clean(body)
    assert kept.renditions[0].body == pdf


def test_a_video_comes_out_without_its_location_and_with_a_clean_poster(tmp_path: Path) -> None:
    source = phone_video(tmp_path / "tour.mp4")
    # The fixture really carries them: MP4 keeps the location as a binary "loci" box.
    markers = (b"loci", b"A fictional tour", b"A phone's camera")
    assert all(marker in source.read_bytes() for marker in markers)

    processed = process_video(source, tmp_path)

    video = processed.renditions[0]
    assert (video.name, video.content_type) == ("video", MP4)
    assert isinstance(video.body, Path)
    cleaned = video.body.read_bytes()
    for marker in markers:
        assert marker not in cleaned
    with av.open(str(video.body)) as container:
        assert "location" not in container.metadata
        assert [stream.type for stream in container.streams] == ["video"]
    assert processed.duration_ms == pytest.approx(2_000, abs=200)
    assert (processed.width, processed.height) == (64, 48)
    posters = [rendition for rendition in processed.renditions if rendition.name != "video"]
    assert len(posters) == len(VARIANT_EDGES) * 2
    for poster in posters:
        assert isinstance(poster.body, bytes)
        assert_clean(poster.body)


def test_a_video_longer_than_the_limit_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(processing, "MAX_VIDEO_SECONDS", 1)

    with pytest.raises(UnprocessableError, match="longer than"):
        process_video(phone_video(tmp_path / "long.mp4"), tmp_path)


def test_a_file_that_isnt_a_video_is_refused(tmp_path: Path) -> None:
    fake = tmp_path / "fake.mp4"
    fake.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)

    with pytest.raises(UnprocessableError, match="readable video"):
        process_video(fake, tmp_path)


def test_processed_results_say_what_they_hold() -> None:
    processed = process_photo(phone_photo(size=(200, 100)), JPEG, now=NOW)

    assert isinstance(processed, Processed)
    assert {rendition.extension for rendition in processed.renditions} == {"webp", "avif"}
