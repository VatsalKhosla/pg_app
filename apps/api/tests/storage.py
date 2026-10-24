"""A stand-in for object storage: everything in memory, nothing signed."""

import asyncio
from typing import TYPE_CHECKING

from app.modules.media.ports import PresignedUpload
from app.modules.media.service import Buckets

if TYPE_CHECKING:
    from datetime import timedelta
    from pathlib import Path

BUCKETS = Buckets(private="private-test", public="public-test", public_base_url="https://cdn.test")


class MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}

    def presign_upload(
        self, bucket: str, key: str, *, content_type: str, max_bytes: int, expires_in: timedelta
    ) -> PresignedUpload:
        return PresignedUpload(
            url=f"https://storage.test/{bucket}",
            fields={"key": key, "Content-Type": content_type, "max": str(max_bytes)},
        )

    def presign_download(
        self, bucket: str, key: str, *, expires_in: timedelta, filename: str | None = None
    ) -> str:
        return f"https://storage.test/{bucket}/{key}?signed={int(expires_in.total_seconds())}"

    async def size(self, bucket: str, key: str) -> int | None:
        found = self.objects.get((bucket, key))
        return None if found is None else len(found[0])

    async def download(self, bucket: str, key: str, target: Path) -> None:
        await asyncio.to_thread(target.write_bytes, self.objects[bucket, key][0])

    async def upload(
        self,
        bucket: str,
        key: str,
        body: bytes | Path,
        *,
        content_type: str,
        cache_control: str | None = None,
        content_disposition: str | None = None,
    ) -> None:
        data = body if isinstance(body, bytes) else await asyncio.to_thread(body.read_bytes)
        self.objects[bucket, key] = (data, content_type)

    async def delete(self, bucket: str, key: str) -> None:
        self.objects.pop((bucket, key), None)
