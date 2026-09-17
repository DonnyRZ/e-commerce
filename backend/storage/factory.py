"""Media storage factory — env-gated, no silent fallbacks."""

from storage.base import MediaStorageProvider
from storage.local import LocalFilesystemStorage
from storage.s3 import S3Storage


def get_media_storage() -> MediaStorageProvider:
    import os

    provider = os.environ.get("MEDIA_STORAGE", "local")
    if provider == "local":
        return LocalFilesystemStorage()
    if provider == "s3":
        return S3Storage()
    raise RuntimeError(f"Unsupported MEDIA_STORAGE: {provider}")
