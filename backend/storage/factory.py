"""Media storage factory — env-gated, no silent fallbacks."""

from storage.base import MediaStorageProvider
from storage.local import LocalFilesystemStorage


def get_media_storage() -> MediaStorageProvider:
    import os

    provider = os.environ.get("MEDIA_STORAGE", "local")
    if provider == "local":
        return LocalFilesystemStorage()
    raise RuntimeError(f"Unsupported MEDIA_STORAGE: {provider}")
