"""Device security, retry isolation, deduplication, and real Web Push encryption."""

import asyncio
import base64
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://unused:unused@localhost:1/test"
)
os.environ.setdefault("JWT_SECRET", "isolated-test-secret")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import http_ece
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from requests import Response
from pywebpush import WebPushException
from sqlalchemy.dialects import postgresql
import admin_push
from scripts.ensure_admin_push_keys import ensure_key


class PushTests(unittest.IsolatedAsyncioTestCase):
    def test_endpoint_allowlist_rejects_ssrf_and_lookalike_hosts(self):
        for endpoint in [
            "http://fcm.googleapis.com/send/1",
            "https://127.0.0.1/secret",
            "https://169.254.169.254/latest/meta-data",
            "https://fcm.googleapis.com.evil.test/send/1",
            "https://fcm.googleapis.com@evil.test/send/1",
            "https://fcm.googleapis.com:8443/send/1",
            "https://fcm.googleapis.com/send/1#fragment",
            "file:///etc/passwd",
        ]:
            with self.subTest(endpoint=endpoint):
                self.assertFalse(admin_push.valid_endpoint(endpoint))
        for host in [
            "fcm.googleapis.com",
            "updates.push.services.mozilla.com",
            "web.push.apple.com",
            "wns.notify.windows.com",
        ]:
            self.assertTrue(admin_push.valid_endpoint(f"https://{host}/send/example"))

    def test_keys_validate_curve_point_and_auth_secret(self):
        key = (
            ec.generate_private_key(ec.SECP256R1())
            .public_key()
            .public_bytes(
                serialization.Encoding.X962,
                serialization.PublicFormat.UncompressedPoint,
            )
        )
        encoded = base64.urlsafe_b64encode(key).decode().rstrip("=")
        self.assertTrue(admin_push.valid_key(encoded, 65))
        self.assertTrue(
            admin_push.valid_key(base64.urlsafe_b64encode(b"a" * 16).decode(), 16)
        )
        self.assertFalse(
            admin_push.valid_key(base64.urlsafe_b64encode(b"a" * 65).decode(), 65)
        )
        self.assertFalse(admin_push.valid_key("invalid!", 16))

    def test_persistent_key_is_not_rotated_and_invalid_key_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "keys" / "vapid.pem"
            ensure_key(path)
            original = path.read_bytes()
            ensure_key(path)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with patch.object(admin_push, "ADMIN_PUSH_ENABLED", True), patch.object(
                admin_push, "VAPID_PRIVATE_KEY_FILE", str(path)
            ):
                self.assertEqual(
                    len(base64.urlsafe_b64decode(admin_push.public_key() + "=")), 65
                )
            path.write_bytes(b"invalid")
            with self.assertRaises(ValueError):
                ensure_key(path)
            self.assertEqual(path.read_bytes(), b"invalid")

    async def test_fanout_queues_every_device_without_network_and_deduplicates_event(
        self,
    ):
        devices = [
            SimpleNamespace(id="device-1", user_id="admin-1", token_version=2),
            SimpleNamespace(id="device-2", user_id="admin-1", token_version=2),
            SimpleNamespace(id="device-3", user_id="admin-2", token_version=1),
        ]
        session = SimpleNamespace(
            scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: devices)),
            execute=AsyncMock(),
        )
        with patch.object(admin_push, "ADMIN_PUSH_ENABLED", True), patch.object(
            admin_push, "send_delivery"
        ) as send:
            count = await admin_push.enqueue_admin_notification(
                session,
                "telegram-message:one",
                "telegram",
                "/admin/telegram-inbox?conversation=abc",
            )
        self.assertEqual(count, 3)
        send.assert_not_called()
        query = str(
            session.scalars.call_args.args[0].compile(dialect=postgresql.dialect())
        )
        self.assertIn("users.is_active IS true", query)
        self.assertIn(
            "admin_push_subscriptions.token_version = users.token_version", query
        )
        statement = session.execute.call_args.args[0].compile(
            dialect=postgresql.dialect()
        )
        self.assertIn(
            "ON CONFLICT ON CONSTRAINT uq_admin_push_delivery_event DO NOTHING",
            str(statement),
        )
        payloads = [
            value
            for key, value in statement.params.items()
            if key.startswith("payload_")
        ]
        self.assertEqual(len(payloads), 3)
        self.assertTrue(
            all(value["title"] == "Chat Telegram baru" for value in payloads)
        )
        self.assertNotIn("customer_name", json.dumps(payloads))

    async def test_disabled_push_does_not_change_existing_business_transactions(self):
        session = SimpleNamespace(execute=AsyncMock(), scalars=AsyncMock())
        with patch.object(admin_push, "ADMIN_PUSH_ENABLED", False):
            self.assertEqual(
                await admin_push.enqueue_admin_notification(
                    session, "event", "order", "/admin/orders"
                ),
                0,
            )
        session.execute.assert_not_called()
        session.scalars.assert_not_called()

    async def test_one_expired_device_does_not_prevent_delivery_to_other_admins(self):
        expired = SimpleNamespace(endpoint="expired", enabled=True)
        healthy = SimpleNamespace(endpoint="healthy", enabled=True)
        delivery1 = SimpleNamespace(attempts=0, status="pending", payload={})
        delivery2 = SimpleNamespace(attempts=0, status="pending", payload={})
        result = SimpleNamespace(
            all=lambda: [(delivery1, expired), (delivery2, healthy)]
        )
        session = SimpleNamespace(
            execute=AsyncMock(side_effect=[None, result]), commit=AsyncMock()
        )
        response = Response()
        response.status_code = 410

        def send(subscription, _payload):
            if subscription.endpoint == "expired":
                raise WebPushException("gone", response=response)

        with patch.object(admin_push, "send_delivery", side_effect=send):
            self.assertEqual(await admin_push.dispatch_pending(session), 2)
        self.assertFalse(expired.enabled)
        self.assertEqual(delivery1.status, "expired")
        self.assertEqual(delivery2.status, "sent")
        session.commit.assert_awaited_once()

    async def test_transient_failure_retries_only_the_failed_device_and_honors_retry_after(
        self,
    ):
        device = SimpleNamespace(endpoint="retry", enabled=True)
        row = SimpleNamespace(attempts=0, status="pending", payload={})
        result = SimpleNamespace(all=lambda: [(row, device)])
        session = SimpleNamespace(
            execute=AsyncMock(side_effect=[None, result]), commit=AsyncMock()
        )
        response = Response()
        response.status_code = 429
        response.headers["Retry-After"] = "120"
        with patch.object(
            admin_push,
            "send_delivery",
            side_effect=WebPushException("busy", response=response),
        ):
            await admin_push.dispatch_pending(session)
        self.assertTrue(device.enabled)
        self.assertEqual(row.status, "pending")
        self.assertEqual(row.attempts, 1)
        self.assertGreaterEqual(
            (row.next_attempt_at - admin_push.utcnow()).total_seconds(), 119
        )

    def test_delivery_is_encrypted_and_signed_for_the_provider(self):
        receiver = ec.generate_private_key(ec.SECP256R1())
        public = receiver.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        auth = os.urandom(16)
        encode = lambda value: base64.urlsafe_b64encode(value).decode().rstrip("=")
        subscription = SimpleNamespace(
            endpoint="https://fcm.googleapis.com/fcm/send/test-device",
            p256dh=encode(public),
            auth=encode(auth),
        )
        response = Response()
        response.status_code = 201
        payload = {"title": "Chat Telegram baru", "url": "/admin/telegram-inbox"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "key.pem"
            ensure_key(path)
            with patch.object(
                admin_push, "VAPID_PRIVATE_KEY_FILE", str(path)
            ), patch.object(
                admin_push, "VAPID_SUBJECT", "https://shanicantik.com"
            ), patch(
                "pywebpush.requests.post", return_value=response
            ) as request:
                admin_push.send_delivery(subscription, payload)
        sent = request.call_args.kwargs
        self.assertNotIn(b"Chat Telegram", sent["data"])
        decoded = http_ece.decrypt(
            sent["data"], private_key=receiver, auth_secret=auth, version="aes128gcm"
        )
        self.assertEqual(json.loads(decoded), payload)
        self.assertTrue(sent["headers"]["Authorization"].startswith("vapid "))
        self.assertEqual(sent["headers"]["Urgency"], "high")


if __name__ == "__main__":
    unittest.main()
