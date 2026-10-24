"""Object storage over S3 (boto3): AWS when deployed, SeaweedFS locally. Signing is local work
(no network); transfers run in a thread, so they don't hold up the event loop."""

import asyncio
import io
import json
from typing import TYPE_CHECKING, Final

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.modules.media.ports import PresignedUpload

if TYPE_CHECKING:
    from datetime import timedelta
    from pathlib import Path

    from types_boto3_s3 import S3Client

    from app.config import Settings

# Backend rules: connect within 3 s, read within 10 s; retry what is safe to retry.
_CONFIG: Final = {
    "connect_timeout": 3,
    "read_timeout": 10,
    "retries": {"mode": "standard", "max_attempts": 3},
    "signature_version": "s3v4",
}


class S3Storage:
    def __init__(self, client: S3Client) -> None:
        self._client = client

    @classmethod
    def from_settings(cls, settings: Settings) -> S3Storage:
        # A custom endpoint (SeaweedFS) is addressed by path; AWS by virtual host.
        style = "path" if settings.s3_endpoint_url else "virtual"
        client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=None
            if settings.s3_access_key_id is None
            else settings.s3_access_key_id.get_secret_value(),
            aws_secret_access_key=None
            if settings.s3_secret_access_key is None
            else settings.s3_secret_access_key.get_secret_value(),
            config=Config(**_CONFIG, s3={"addressing_style": style}),  # type: ignore[arg-type]
        )
        return cls(client)

    def presign_upload(
        self, bucket: str, key: str, *, content_type: str, max_bytes: int, expires_in: timedelta
    ) -> PresignedUpload:
        post = self._client.generate_presigned_post(
            bucket,
            key,
            Fields={"Content-Type": content_type},
            Conditions=[{"Content-Type": content_type}, ["content-length-range", 1, max_bytes]],
            ExpiresIn=int(expires_in.total_seconds()),
        )
        return PresignedUpload(
            url=post["url"], fields={k: str(v) for k, v in post["fields"].items()}
        )

    def presign_download(
        self, bucket: str, key: str, *, expires_in: timedelta, filename: str | None = None
    ) -> str:
        params: dict[str, str] = {"Bucket": bucket, "Key": key}
        if filename is not None:
            params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
        return self._client.generate_presigned_url(
            "get_object", Params=params, ExpiresIn=int(expires_in.total_seconds())
        )

    async def size(self, bucket: str, key: str) -> int | None:
        try:
            head = await asyncio.to_thread(self._client.head_object, Bucket=bucket, Key=key)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        return head["ContentLength"]

    async def download(self, bucket: str, key: str, target: Path) -> None:
        await asyncio.to_thread(self._client.download_file, bucket, key, str(target))

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
        extra = {"ContentType": content_type}
        if cache_control is not None:
            extra["CacheControl"] = cache_control
        if content_disposition is not None:
            extra["ContentDisposition"] = content_disposition
        if isinstance(body, bytes):
            await asyncio.to_thread(
                self._client.upload_fileobj, io.BytesIO(body), bucket, key, ExtraArgs=extra
            )
        else:
            await asyncio.to_thread(
                self._client.upload_file, str(body), bucket, key, ExtraArgs=extra
            )

    async def delete(self, bucket: str, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=bucket, Key=key)

    def ensure_local_buckets(self, *, private: str, public: str, web_origin: str) -> list[str]:
        """Create the buckets, for local development and tests (Terraform does it when
        deployed): anyone may read the public bucket's media, as through the CDN, and the web
        app may post uploads to the private one. Returns the buckets it created."""
        created = []
        for bucket in (private, public):
            try:
                self._client.head_bucket(Bucket=bucket)
            except ClientError:
                self._client.create_bucket(Bucket=bucket)
                created.append(bucket)
        readable = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "PublicMedia",
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{public}/media/*"],
                }
            ],
        }
        self._client.put_bucket_policy(Bucket=public, Policy=json.dumps(readable))
        self._client.put_bucket_cors(
            Bucket=private,
            CORSConfiguration={
                "CORSRules": [
                    {
                        "AllowedOrigins": [web_origin],
                        "AllowedMethods": ["POST"],
                        "AllowedHeaders": ["*"],
                        "MaxAgeSeconds": 600,
                    }
                ]
            },
        )
        return created
