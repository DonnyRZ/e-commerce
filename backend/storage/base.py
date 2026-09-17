from abc import ABC, abstractmethod


class MediaStorageProvider(ABC):
    """Media storage boundary — replaceable with S3-compatible storage later
    without database redesign (rows store provider + storage_key only)."""

    name: str = "abstract"

    @abstractmethod
    async def save(self, data: bytes, key: str, content_type: str) -> None:
        ...

    @abstractmethod
    def resolve_path(self, key: str) -> str:
        """Local filesystem path for reading (serving). Local provider only."""
        ...

    @abstractmethod
    def public_url(self, key: str) -> str:
        """Public URL for browser delivery, when the provider supports it."""
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        ...
