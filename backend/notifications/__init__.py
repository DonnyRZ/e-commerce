"""Notification boundary — MockNotificationProvider only.

Notifications fire AFTER the critical DB transaction commits; a failure
here must never roll back an order/payment. Callers pass only safe fields
(no secrets, no credentials).
"""

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger("notifications")


class NotificationProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    async def send(self, event: str, payload: dict) -> None:
        ...


class MockNotificationProvider(NotificationProvider):
    """Dev provider — logs events instead of sending email."""

    name = "mock"

    async def send(self, event: str, payload: dict) -> None:
        logger.info("MOCK NOTIFY %s %s", event, payload)


def get_notifier() -> NotificationProvider:
    from config import NOTIFICATION_PROVIDER

    if NOTIFICATION_PROVIDER == "mock":
        return MockNotificationProvider()
    raise RuntimeError(f"Unsupported NOTIFICATION_PROVIDER: {NOTIFICATION_PROVIDER}")


async def notify(event: str, payload: dict) -> None:
    try:
        await get_notifier().send(event, payload)
    except Exception:
        logger.exception("notification %s failed (ignored)", event)
