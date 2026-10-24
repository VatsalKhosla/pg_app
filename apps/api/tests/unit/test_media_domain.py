"""The media rules (step 2.3): what each upload takes, an asset's life, file signatures, capture
times and variant sizes."""

from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.media.domain.assets import (
    JPEG,
    MIB,
    MP4,
    PDF,
    PNG,
    RULES,
    WEBP,
    AssetStatus,
    Purpose,
    Visibility,
    can_move,
    upload_problems,
    variant_size,
)
from app.modules.media.domain.capture import taken_at
from app.modules.media.domain.sniff import sniff

UPLOADED = datetime(2027, 6, 12, 12, 0, tzinfo=UTC)


def test_listing_media_are_public_and_documents_private() -> None:
    assert RULES[Purpose.LISTING_PHOTO].visibility is Visibility.PUBLIC
    assert RULES[Purpose.LISTING_VIDEO].visibility is Visibility.PUBLIC
    assert RULES[Purpose.DOCUMENT].visibility is Visibility.PRIVATE


@pytest.mark.parametrize(
    ("purpose", "content_type", "size", "allowed"),
    [
        (Purpose.LISTING_PHOTO, JPEG, 15 * MIB, True),
        (Purpose.LISTING_PHOTO, JPEG, 15 * MIB + 1, False),
        (Purpose.LISTING_PHOTO, "image/svg+xml", 100, False),
        (Purpose.LISTING_PHOTO, "image/heic", 100, False),
        (Purpose.LISTING_PHOTO, MP4, 100, False),
        (Purpose.LISTING_VIDEO, MP4, 200 * MIB, True),
        (Purpose.LISTING_VIDEO, MP4, 200 * MIB + 1, False),
        (Purpose.DOCUMENT, PDF, 10 * MIB, True),
        (Purpose.DOCUMENT, WEBP, 100, False),
        (Purpose.DOCUMENT, PNG, 0, False),
    ],
)
def test_each_upload_takes_its_own_types_and_sizes(
    purpose: Purpose, content_type: str, size: int, allowed: bool
) -> None:
    assert (upload_problems(purpose, content_type, size) == []) is allowed


def test_an_asset_is_processed_once_and_then_stays_as_it_is() -> None:
    assert can_move(AssetStatus.AWAITING_UPLOAD, AssetStatus.PROCESSING)
    assert can_move(AssetStatus.PROCESSING, AssetStatus.READY)
    assert can_move(AssetStatus.PROCESSING, AssetStatus.REJECTED)
    assert not can_move(AssetStatus.AWAITING_UPLOAD, AssetStatus.READY)
    assert not any(can_move(AssetStatus.READY, target) for target in AssetStatus)
    assert not any(can_move(AssetStatus.REJECTED, target) for target in AssetStatus)


@pytest.mark.parametrize(
    ("head", "found"),
    [
        (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00", JPEG),
        (b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR", PNG),
        (b"RIFF\x24\x00\x00\x00WEBPVP8 ", WEBP),
        (b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00", MP4),
        (b"\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00", MP4),
        (b"%PDF-1.7\n%\xe2\xe3", PDF),
        (b"<svg xmlns='http://www.w3.org/2000/svg'", None),
        (b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00", None),
        (b"GIF89a\x01\x00\x01\x00", None),
        (b"", None),
    ],
)
def test_a_file_is_what_its_first_bytes_say(head: bytes, found: str | None) -> None:
    assert sniff(head) == found


@pytest.mark.parametrize(
    ("stamp", "offset", "moment"),
    [
        # Without an offset, India's time.
        ("2027:06:12 10:30:05", None, datetime(2027, 6, 12, 5, 0, 5, tzinfo=UTC)),
        ("2027:06:12 10:30:05", "+05:30", datetime(2027, 6, 12, 5, 0, 5, tzinfo=UTC)),
        ("2027:06:12 08:00:00", "+01:00", datetime(2027, 6, 12, 7, 0, 0, tzinfo=UTC)),
        ("2027:06:12 10:30:05\x00", None, datetime(2027, 6, 12, 5, 0, 5, tzinfo=UTC)),
        # After the upload, impossible, or missing: no capture time.
        ("2027:06:13 10:00:00", None, None),
        ("1999:12:31 23:00:00", "+00:00", None),
        ("2027:02:30 10:00:00", None, None),
        ("0000:00:00 00:00:00", None, None),
        (None, None, None),
    ],
)
def test_a_capture_time_is_read_in_its_zone_and_only_when_plausible(
    stamp: str | None, offset: str | None, moment: datetime | None
) -> None:
    assert taken_at(stamp, offset, before=UPLOADED) == moment


@given(
    st.integers(min_value=1, max_value=20_000),
    st.integers(min_value=1, max_value=20_000),
    st.sampled_from([160, 480, 1080, 2048]),
)
def test_a_variant_fits_its_edge_keeps_its_shape_and_never_grows(
    width: int, height: int, edge: int
) -> None:
    fitted = variant_size(width, height, edge)

    assert max(fitted) <= max(edge, 1)
    assert fitted[0] <= width
    assert fitted[1] <= height
    if max(width, height) <= edge:
        assert fitted == (width, height)
    else:
        # The shape is kept to within a pixel of rounding.
        assert abs(fitted[0] * height - fitted[1] * width) <= max(width, height)
