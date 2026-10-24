"""What the media module needs from object storage (CLAUDE.md: integrations behind ports). The
S3 adapter serves AWS and, locally, SeaweedFS; tests use a stand-in."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import timedelta
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class PresignedUpload:
    """A form the browser posts the file to, straight to storage: ``url`` and its ``fields``,
    the file last. Storage itself refuses another content type or a file over the size."""

    url: str
    fields: dict[str, str]


class ObjectStorage(Protocol):
    def presign_upload(
        self, bucket: str, key: str, *, content_type: str, max_bytes: int, expires_in: timedelta
    ) -> PresignedUpload: ...

    def presign_download(
        self, bucket: str, key: str, *, expires_in: timedelta, filename: str | None = None
    ) -> str: ...

    async def size(self, bucket: str, key: str) -> int | None:
        """The object's size in bytes, or None if there is no such object."""
        ...

    async def download(self, bucket: str, key: str, target: Path) -> None: ...

    async def upload(
        self,
        bucket: str,
        key: str,
        body: bytes | Path,
        *,
        content_type: str,
        cache_control: str | None = None,
        content_disposition: str | None = None,
    ) -> None: ...

    async def delete(self, bucket: str, key: str) -> None:
        """Delete the object; deleting one that isn't there is fine."""
        ...
