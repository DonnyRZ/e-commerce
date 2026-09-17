"""Post-commit notification boundary.

Notification failures are intentionally isolated from checkout/payment
transactions, but production uses a real SMTP provider rather than silently
logging a mock message.
"""

import asyncio
import logging
import smtplib
import ssl
from abc import ABC, abstractmethod
from email.message import EmailMessage

logger = logging.getLogger("notifications")


class NotificationProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    async def send(self, event: str, payload: dict) -> None:
        ...


class MockNotificationProvider(NotificationProvider):
    name = "mock"

    async def send(self, event: str, payload: dict) -> None:
        logger.info("MOCK NOTIFY %s %s", event, payload)


class SMTPNotificationProvider(NotificationProvider):
    name = "smtp"

    def __init__(self):
        from config import (
            SMTP_FROM,
            SMTP_HOST,
            SMTP_PASSWORD,
            SMTP_PORT,
            SMTP_USE_TLS,
            SMTP_USERNAME,
        )

        self.host = SMTP_HOST
        self.port = SMTP_PORT
        self.username = SMTP_USERNAME
        self.password = SMTP_PASSWORD
        self.sender = SMTP_FROM
        self.use_tls = SMTP_USE_TLS

    @staticmethod
    def _message(event: str, payload: dict) -> tuple[str, str, str | None]:
        recipient = payload.get("email") or payload.get("recipient_email")
        order_number = payload.get("order_number") or payload.get("merchant_trans_id", "")
        amount = payload.get("amount")
        currency = payload.get("currency", "")
        if event == "password.reset":
            return (
                "Reset your password",
                f"Use this link to reset your password:\n\n{payload.get('reset_url', '')}\n\n"
                "If you did not request this, you can ignore this email.",
                recipient,
            )
        if event == "order.placed":
            return (
                f"Order received: {order_number}",
                f"We received your order {order_number}.\n"
                f"Amount: {amount} {currency}. Payment is still pending.",
                recipient,
            )
        if event == "order.paid":
            return (
                f"Payment confirmed: {order_number}",
                f"Payment for order {order_number} was confirmed.\n"
                f"Amount: {amount} {currency}.",
                recipient,
            )
        if event == "order.payment_failed":
            return (
                f"Payment not completed: {order_number}",
                f"Payment for order {order_number} was not completed. Please try again.",
                recipient,
            )
        return ("Store notification", f"Event: {event}\nOrder: {order_number}", recipient)

    def _send_sync(self, message: EmailMessage) -> None:
        context = ssl.create_default_context()
        with smtplib.SMTP(self.host, self.port, timeout=20) as server:
            if self.use_tls:
                server.starttls(context=context)
            if self.username:
                server.login(self.username, self.password)
            server.send_message(message)

    async def send(self, event: str, payload: dict) -> None:
        subject, body, recipient = self._message(event, payload)
        if not recipient:
            logger.warning("notification %s skipped: no recipient", event)
            return
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.sender
        message["To"] = recipient
        message.set_content(body)
        await asyncio.to_thread(self._send_sync, message)


def get_notifier() -> NotificationProvider:
    from config import NOTIFICATION_PROVIDER

    if NOTIFICATION_PROVIDER == "mock":
        return MockNotificationProvider()
    if NOTIFICATION_PROVIDER == "smtp":
        return SMTPNotificationProvider()
    raise RuntimeError(f"Unsupported NOTIFICATION_PROVIDER: {NOTIFICATION_PROVIDER}")


async def notify(event: str, payload: dict) -> None:
    try:
        await get_notifier().send(event, payload)
    except Exception:
        logger.exception("notification %s failed (ignored)", event)
