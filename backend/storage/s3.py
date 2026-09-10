"""S3-compatible media storage for production/CDN delivery."""

import asyncio
import os
from urllib.parse import quote

import boto3

from storage.base import MediaStorageProvider


class S3Storage(MediaStorageProvider):
    name = "s3"

    def __init__(self):
        self.bucket = os.environ["S3_BUCKET"]
        self.region = os.environ.get("S3_REGION") or None
        self.endpoint_url = os.environ.get("S3_ENDPOINT_URL") or None
        self.public_base_url = os.environ["S3_PUBLIC_BASE_URL"].rstrip("/")
        self.client = boto3.client(
            "s3",
            region_name=self.region,
            endpoint_url=self.endpoint_url,
            aws_access_key_id=os.environ.get("S3_ACCESS_KEY_ID") or None,
            aws_secret_access_key=os.environ.get("S3_SECRET_ACCESS_KEY") or None,
        )

    async def save(self, data: bytes, key: str, content_type: str) -> None:
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            CacheControl="public, max-age=31536000, immutable",
        )

    def resolve_path(self, key: str) -> str:
        raise RuntimeError("S3 media has no local filesystem path")

    def public_url(self, key: str) -> str:
        return f"{self.public_base_url}/{quote(key, safe='')}"

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=key)
