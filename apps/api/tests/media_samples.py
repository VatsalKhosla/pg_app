"""Sample uploads for the media tests: a phone photo and a phone video that carry what phones
put in them (an orientation, the time and a GPS position; a location tag), and a check that
none of it survived. Every position here is made up."""

import io
from pathlib import Path

import av
from PIL import ExifTags, Image

GPS = {
    ExifTags.GPS.GPSLatitudeRef: "N",
    ExifTags.GPS.GPSLatitude: (12.0, 34.0, 56.0),
    ExifTags.GPS.GPSLongitudeRef: "E",
    ExifTags.GPS.GPSLongitude: (65.0, 43.0, 21.0),
}
XMP = (
    b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-'
    b'syntax-ns#"><rdf:Description xmlns:exif="http://ns.adobe.com/exif/1.0/" exif:GPSLatitude='
    b'"12,34.9N"/></rdf:RDF></x:xmpmeta>'
)


def phone_photo(*, size: tuple[int, int] = (1200, 900), fmt: str = "JPEG") -> bytes:
    """A photo as phones save one: turned by an orientation tag, with a GPS position, the time
    it was taken (in India, without an offset) and XMP."""
    image = Image.new("RGB", size, (180, 120, 60))
    exif = Image.Exif()
    exif[ExifTags.Base.Orientation] = 6  # shown turned 90° clockwise
    exif[ExifTags.Base.Make] = "A phone"
    exif.get_ifd(ExifTags.IFD.Exif)[ExifTags.Base.DateTimeOriginal] = "2027:06:12 10:30:05"
    exif[ExifTags.IFD.GPSInfo] = GPS
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, exif=exif, xmp=XMP)
    return buffer.getvalue()


def assert_clean(body: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(body))
    assert len(image.getexif()) == 0
    assert "exif" not in image.info
    assert "xmp" not in image.info
    for marker in (b"Exif", b"EXIF", b"GPSLatitude", b"xmpmeta", b"A phone"):
        assert marker not in body
    return image


def phone_video(path: Path, *, seconds: int = 2, size: tuple[int, int] = (64, 48)) -> Path:
    """A short MP4 with a location tag, as phones write one, and a title."""
    with av.open(str(path), "w", format="mp4") as container:
        container.metadata["location"] = "+12.5822+065.7225/"
        container.metadata["title"] = "A fictional tour"
        stream = container.add_stream("mpeg4", rate=10)
        stream.width, stream.height = size
        stream.pix_fmt = "yuv420p"
        stream.metadata["handler_name"] = "A phone's camera"
        image = Image.new("RGB", size, (30, 160, 90))
        for _ in range(seconds * 10):
            # PyAV declares from_image without types.
            frame = av.VideoFrame.from_image(image)  # type: ignore[no-untyped-call]
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path
