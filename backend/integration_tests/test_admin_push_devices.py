"""Run against an isolated Compose database; never contact Telegram/FCM."""

import base64
import os
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from sqlalchemy import delete, select, func
from auth import hash_password
import admin_push
from db.models import (
    AdminPushDelivery,
    AdminPushSubscription,
    Cart,
    Order,
    Product,
    ProductVariant,
    TelegramBusinessConnection,
    TelegramInboxMessage,
    TelegramUpdateReceipt,
    User,
    utcnow,
)
from checkout import service as checkout_service
from db.session import SessionLocal, engine
from routers.auth import router as auth_router
from routers.admin_push import router as push_router
from routers import telegram
from scripts.ensure_admin_push_keys import ensure_key
from config import TELEGRAM_STORE_USERNAME


class AdminDeviceIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.prefix = secrets.token_hex(6)
        self.users = []
        self.clients = []
        self.update_id = secrets.randbelow(10**12)
        self.connection_id = "push-test-" + self.prefix
        self.order_ids = []
        self.directory = tempfile.TemporaryDirectory()
        key_path = Path(self.directory.name) / "key.pem"
        ensure_key(key_path)
        self.patches = [
            patch.object(admin_push, "ADMIN_PUSH_ENABLED", True),
            patch.object(admin_push, "VAPID_PRIVATE_KEY_FILE", str(key_path)),
            patch.object(telegram, "TELEGRAM_BOT_TOKEN", "isolated-fake-token"),
            patch.object(
                telegram, "TELEGRAM_WEBHOOK_SECRET", "isolated-webhook-secret"
            ),
            patch.object(telegram, "TELEGRAM_INQUIRIES_ENABLED", False),
        ]
        for item in self.patches:
            item.start()
        app = FastAPI()
        app.include_router(auth_router)
        app.include_router(push_router)
        app.include_router(telegram.router)
        async with SessionLocal() as session:
            for index, role in enumerate(["admin", "admin", "customer"]):
                user = User(
                    email=f"push-{self.prefix}-{index}@example.com",
                    role=role,
                    password_hash=hash_password("LocalAuditPass123!"),
                    full_name="Local push test",
                )
                session.add(user)
                await session.flush()
                self.users.append(user)
            session.add(
                TelegramBusinessConnection(
                    connection_id=self.connection_id,
                    business_user_id="999999",
                    username=TELEGRAM_STORE_USERNAME,
                    is_enabled=True,
                    can_reply=True,
                    can_read_messages=True,
                )
            )
            await session.commit()
        for index, user in enumerate(self.users):
            client = httpx.AsyncClient(
                transport=httpx.ASGITransport(
                    app=app, client=(f"198.51.100.{secrets.randbelow(250) + 1}", 1234)
                ),
                base_url="http://testserver",
            )
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": user.email, "password": "LocalAuditPass123!"},
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.clients.append(client)
        raw = (
            ec.generate_private_key(ec.SECP256R1())
            .public_key()
            .public_bytes(
                serialization.Encoding.X962,
                serialization.PublicFormat.UncompressedPoint,
            )
        )
        encode = lambda value: base64.urlsafe_b64encode(value).decode().rstrip("=")
        self.keys = {"p256dh": encode(raw), "auth": encode(os.urandom(16))}
        self.endpoints = [
            f"https://fcm.googleapis.com/fcm/send/{self.prefix}-{index}"
            for index in range(3)
        ]

    async def asyncTearDown(self):
        for client in self.clients:
            await client.aclose()
        async with SessionLocal() as session:
            await session.execute(delete(Order).where(Order.id.in_(self.order_ids)))
            await session.execute(
                delete(Cart).where(Cart.user_id.in_([user.id for user in self.users]))
            )
            await session.execute(
                delete(User).where(User.id.in_([user.id for user in self.users]))
            )
            await session.execute(
                delete(TelegramBusinessConnection).where(
                    TelegramBusinessConnection.connection_id == self.connection_id
                )
            )
            await session.execute(
                delete(TelegramUpdateReceipt).where(
                    TelegramUpdateReceipt.update_id.in_(
                        [self.update_id, self.update_id + 1, self.update_id + 2]
                    )
                )
            )
            await session.commit()
        await engine.dispose()
        for item in reversed(self.patches):
            item.stop()
        self.directory.cleanup()

    async def mutate(self, client, method, path, data):
        return await client.request(
            method,
            "/api/v1/admin/push" + path,
            json=data,
            headers={"X-CSRF-Token": client.cookies.get("csrf_token", "")},
        )

    async def register_devices(self):
        for index, endpoint in enumerate(self.endpoints):
            client = self.clients[0 if index < 2 else 1]
            response = await self.mutate(
                client,
                "POST",
                "/subscriptions",
                {"endpoint": endpoint, "keys": self.keys},
            )
            self.assertEqual(response.status_code, 200, response.text)
            # Reopening an installed app resynchronizes, never creates a duplicate.
            self.assertEqual(
                (
                    await self.mutate(
                        client,
                        "POST",
                        "/subscriptions",
                        {"endpoint": endpoint, "keys": self.keys},
                    )
                ).status_code,
                200,
            )

    async def test_new_checkout_order_notifies_devices_once_after_commit(self):
        await self.register_devices()
        async with SessionLocal() as session:
            product = await session.scalar(
                select(Product).where(Product.status == "active")
            )
            variant = await session.scalar(
                select(ProductVariant).where(ProductVariant.product_id == product.id)
            )
            cart = Cart(user_id=self.users[2].id)
            session.add(cart)
            await session.flush()
            totals = {
                "shipping": {"code": "manual"},
                "subtotal": product.base_price,
                "shipping_amount": 0,
                "grand_total": product.base_price,
                "items": [
                    {
                        "product": product,
                        "variant": variant,
                        "row": type("Item", (), {"quantity": 1})(),
                        "unit_price": product.base_price,
                        "line_total": product.base_price,
                    }
                ],
            }
            with patch.object(checkout_service, "CHECKOUT_ENABLED", True), patch.object(
                checkout_service, "compute_cart_totals", AsyncMock(return_value=totals)
            ):
                args = dict(
                    user=self.users[2],
                    cart=cart,
                    contact_email=self.users[2].email,
                    address_snapshot={"recipient_name": "Local test"},
                    shipping_method="manual",
                    idempotency_key="push-order-" + self.prefix,
                    locale="en",
                )
                order, created = await checkout_service.create_order(session, **args)
                self.assertTrue(created)
                self.order_ids.append(order.id)
                await session.commit()
                again, created = await checkout_service.create_order(session, **args)
                self.assertFalse(created)
                self.assertEqual(again.id, order.id)
                deliveries = (
                    await session.scalars(
                        select(AdminPushDelivery).where(
                            AdminPushDelivery.user_id.in_(
                                [user.id for user in self.users]
                            )
                        )
                    )
                ).all()
                self.assertEqual(len(deliveries), 3)
                self.assertTrue(
                    all(
                        item.payload["kind"] == "order"
                        and item.payload["url"] == "/admin/orders/" + order.order_number
                        for item in deliveries
                    )
                )

    async def test_api_requires_admin_csrf_and_ownership(self):
        await self.register_devices()
        response = await self.mutate(
            self.clients[2],
            "POST",
            "/subscriptions",
            {"endpoint": self.endpoints[0], "keys": self.keys},
        )
        self.assertEqual(response.status_code, 403)
        response = await self.clients[0].post(
            "/api/v1/admin/push/subscriptions",
            json={"endpoint": self.endpoints[0], "keys": self.keys},
        )
        self.assertEqual(response.status_code, 403)
        response = await self.mutate(
            self.clients[0],
            "POST",
            "/subscriptions",
            {"endpoint": "https://127.0.0.1/internal", "keys": self.keys},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            (
                await self.mutate(
                    self.clients[1], "POST", "/test", {"endpoint": self.endpoints[0]}
                )
            ).status_code,
            404,
        )
        await self.mutate(
            self.clients[1], "DELETE", "/subscriptions", {"endpoint": self.endpoints[0]}
        )
        async with SessionLocal() as session:
            device = await session.scalar(
                select(AdminPushSubscription).where(
                    AdminPushSubscription.endpoint == self.endpoints[0]
                )
            )
            self.assertTrue(device.enabled)
            self.assertEqual(
                await session.scalar(
                    select(func.count())
                    .select_from(AdminPushSubscription)
                    .where(
                        AdminPushSubscription.user_id.in_([u.id for u in self.users])
                    )
                ),
                3,
            )
        self.assertEqual(
            (
                await self.mutate(
                    self.clients[0], "POST", "/test", {"endpoint": self.endpoints[0]}
                )
            ).status_code,
            200,
        )

    async def test_webhook_fanout_duplicate_edit_outbound_and_unsubscribe(self):
        await self.register_devices()
        message = {
            "business_connection_id": self.connection_id,
            "message_id": 1,
            "date": int(utcnow().timestamp()),
            "chat": {"type": "private", "id": 123456},
            "from": {"id": 123456, "first_name": "Private customer"},
            "text": "Private customer message",
        }

        async def webhook(data):
            return await self.clients[0].post(
                "/api/v1/telegram/webhook",
                json=data,
                headers={"X-Telegram-Bot-Api-Secret-Token": "isolated-webhook-secret"},
            )

        for _ in range(2):
            response = await webhook(
                {"update_id": self.update_id, "business_message": message}
            )
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            (
                await webhook(
                    {
                        "update_id": self.update_id + 1,
                        "edited_business_message": {
                            **message,
                            "text": "Edited private text",
                        },
                    }
                )
            ).status_code,
            200,
        )
        self.assertEqual(
            (
                await webhook(
                    {
                        "update_id": self.update_id + 2,
                        "business_message": {
                            **message,
                            "message_id": 2,
                            "from": {"id": 999999},
                            "text": "Admin reply",
                        },
                    }
                )
            ).status_code,
            200,
        )
        async with SessionLocal() as session:
            rows = (
                await session.scalars(
                    select(AdminPushDelivery).where(
                        AdminPushDelivery.user_id.in_([u.id for u in self.users])
                    )
                )
            ).all()
            self.assertEqual(len(rows), 3)
            self.assertEqual(len({row.subscription_id for row in rows}), 3)
            self.assertTrue(
                all("Private customer" not in str(row.payload) for row in rows)
            )
            transcript = await session.scalar(
                select(TelegramInboxMessage).where(
                    TelegramInboxMessage.connection_id == self.connection_id,
                    TelegramInboxMessage.telegram_message_id == 1,
                )
            )
            self.assertTrue(
                all(
                    row.payload["url"].endswith(transcript.conversation_id)
                    for row in rows
                )
            )
        await self.mutate(
            self.clients[0], "DELETE", "/subscriptions", {"endpoint": self.endpoints[0]}
        )
        with patch.object(admin_push, "send_delivery") as send:
            async with SessionLocal() as session:
                self.assertEqual(await admin_push.dispatch_pending(session), 2)
            async with SessionLocal() as session:
                self.assertEqual(await admin_push.dispatch_pending(session), 0)
            self.assertEqual(send.call_count, 2)
            self.assertEqual(
                {call.args[0].endpoint for call in send.call_args_list},
                set(self.endpoints[1:]),
            )

    async def test_transaction_rollback_and_revoked_admin_do_not_notify(self):
        await self.register_devices()
        async with SessionLocal() as session:
            self.assertEqual(
                await admin_push.enqueue_admin_notification(
                    session, "rollback:" + self.prefix, "order", "/admin/orders"
                ),
                3,
            )
            await session.rollback()
        async with SessionLocal() as session:
            self.assertEqual(
                await session.scalar(
                    select(func.count())
                    .select_from(AdminPushDelivery)
                    .where(AdminPushDelivery.event_key == "rollback:" + self.prefix)
                ),
                0,
            )
            user1 = await session.get(User, self.users[0].id)
            user1.token_version += 1
            user2 = await session.get(User, self.users[1].id)
            user2.role = "customer"
            await session.commit()
            self.assertEqual(
                await admin_push.enqueue_admin_notification(
                    session, "revoked:" + self.prefix, "order", "/admin/orders"
                ),
                0,
            )

    async def test_voice_message_is_visible_and_notifies_every_device(self):
        await self.register_devices()
        response = await self.clients[0].post(
            "/api/v1/telegram/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": "isolated-webhook-secret"},
            json={
                "update_id": self.update_id,
                "business_message": {
                    "business_connection_id": self.connection_id,
                    "message_id": 1,
                    "date": int(utcnow().timestamp()),
                    "chat": {"type": "private", "id": 123456},
                    "from": {"id": 123456},
                    "voice": {"file_id": "private-file-id", "duration": 4},
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        async with SessionLocal() as session:
            transcript = await session.scalar(
                select(TelegramInboxMessage).where(
                    TelegramInboxMessage.connection_id == self.connection_id
                )
            )
            self.assertEqual(transcript.message_type, "voice")
            self.assertIn("Pesan suara", transcript.text)
            count = await session.scalar(
                select(func.count())
                .select_from(AdminPushDelivery)
                .where(AdminPushDelivery.user_id.in_([u.id for u in self.users]))
            )
            self.assertEqual(count, 3)


if __name__ == "__main__":
    unittest.main()
