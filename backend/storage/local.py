"""LocalFilesystemStorage — development/VPS media storage.

Files live under MEDIA_ROOT (default /app/backend/uploads) and are served
through the backend media route (Nginx can map it directly on the VPS).
Keys are uuid-based — original filenames never become storage paths.
"""

import os
from pathlib import Path

from storage.base import MediaStorageProvider

MEDIA_ROOT = os.environ.get("MEDIA_ROOT", "/app/backend/uploads")


class LocalFilesystemStorage(MediaStorageProvider):
    name = "local"

    def __init__(self, root: str = MEDIA_ROOT):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    async def save(self, data: bytes, key: str, content_type: str) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def resolve_path(self, key: str) -> str:
        # storage keys are generated server-side (uuid hex + allowlisted ext)
        safe = os.path.basename(key)
        return str(self.root / safe)

    def public_url(self, key: str) -> str:
        # Local media is intentionally delivered through the authenticated
        # application's media route so the frontend does not need filesystem
        # knowledge.
        return ""

    async def delete(self, key: str) -> None:
        try:
            os.remove(self.resolve_path(key))
        except FileNotFoundError:
            pass
