"""Isolated regression tests: no DB, network, seed fixtures, or production writes.

Run: backend/.venv/Scripts/python.exe -m unittest discover -s backend/unit_tests -v
"""
import os
import sys
import unittest
from pathlib import Path
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://unused:unused@127.0.0.1:1/audit")
os.environ.setdefault("JWT_SECRET", "isolated-test-secret-never-used-for-real-auth")
import routers.telegram as router
import telegram_inquiries as delivery
import routers.manual_orders as orders
from db.models import Cart, CartItem, utcnow

REF = "SC-" + "A" * 32

def fixture():
    inquiry = SimpleNamespace(reference=REF, status="pending", snapshot={"items": []},
        expires_at=utcnow()+timedelta(days=1), locale="id", delivered_at=None,
        telegram_connection_id=None, telegram_chat_id=None, cart_id="cart")
    connection = SimpleNamespace(is_enabled=True, username=router._normalized_username(router.TELEGRAM_STORE_USERNAME),
        can_reply=True, can_read_messages=True, business_user_id="999")
    session = SimpleNamespace(get=AsyncMock(return_value=connection), scalar=AsyncMock(return_value=inquiry),
        commit=AsyncMock(), rollback=AsyncMock())
    message = {"business_connection_id": "connection", "chat": {"type": "private", "id": 123},
        "from": {"id": 123}, "text": REF}
    return session, inquiry, message

class Recovery(unittest.IsolatedAsyncioTestCase):
    async def test_snapshot_retains_cart_row_identity_for_safe_reconciliation(self):
        snapshot = delivery.make_snapshot({
            "items": [{
                "id": "cart-row",
                "product_id": "product",
                "variant_id": "variant",
                "quantity": 2,
            }],
        }, "id")
        self.assertEqual(snapshot["items"][0]["_cart_item_id"], "cart-row")
        self.assertEqual(snapshot["items"][0]["_cart_product_id"], "product")
        self.assertEqual(snapshot["items"][0]["_cart_variant_id"], "variant")

    async def test_successful_inquiry_removes_only_submitted_quantities(self):
        remaining = SimpleNamespace(quantity=5)
        exact = SimpleNamespace(quantity=2)
        session = SimpleNamespace(
            scalar=AsyncMock(side_effect=[SimpleNamespace(id="cart"), remaining, exact, None]),
            delete=AsyncMock(),
        )
        await router._remove_submitted_cart_quantities(session, "cart", [
            {"_cart_item_id": "a", "_cart_product_id": "p1", "_cart_variant_id": "v1", "quantity": 2},
            {"_cart_item_id": "b", "_cart_product_id": "p2", "_cart_variant_id": "v2", "quantity": 2},
            {"_cart_item_id": "removed", "_cart_product_id": "p3", "_cart_variant_id": "v3", "quantity": 1},
            {"_cart_item_id": "invalid", "quantity": -1},
        ])
        self.assertEqual(remaining.quantity, 3)
        session.delete.assert_awaited_once_with(exact)
        self.assertEqual(session.scalar.await_count, 4)

    async def test_old_snapshot_without_cart_item_identity_does_not_delete(self):
        session = SimpleNamespace(scalar=AsyncMock())
        await router._remove_submitted_cart_quantities(session, "cart", [
            {"quantity": 3, "_cart_product_id": "p", "_cart_variant_id": "v"},
        ])
        session.scalar.assert_awaited_once()
        self.assertIs(session.scalar.await_args.args[0].column_descriptions[0]["entity"], Cart)

    async def test_timeout_requires_new_customer_update_not_duplicate_webhook(self):
        session, inquiry, message = fixture()
        with patch.object(router, "send_inquiry", AsyncMock(side_effect=TimeoutError)) as send, \
             patch.object(router, "_remove_submitted_cart_quantities", AsyncMock()) as reconcile:
            await router._handle_business_message(session, message, 10)
            reconcile.assert_not_awaited()
            self.assertEqual(inquiry.status, "unknown")
            send.side_effect = None
            await router._handle_business_message(session, message, 10)
            self.assertEqual(send.await_count, 1)
            await router._handle_business_message(session, message, 11)
            self.assertEqual(send.await_count, 2)
            self.assertEqual(inquiry.status, "sent")
            reconcile.assert_awaited_once_with(session, "cart", [])

    async def test_stale_sending_recovered_only_by_new_update(self):
        session, inquiry, message = fixture()
        inquiry.status = "sending"
        inquiry.snapshot["_delivery"] = {"started": 0, "update_id": 10}
        with patch.object(router, "send_inquiry", AsyncMock()) as send, \
             patch.object(router, "_remove_submitted_cart_quantities", AsyncMock()) as reconcile:
            await router._handle_business_message(session, message, 10)
            self.assertEqual(inquiry.status, "unknown")
            send.assert_not_awaited()
            reconcile.assert_not_awaited()
            await router._handle_business_message(session, message, 11)
            send.assert_awaited_once()
            reconcile.assert_awaited_once_with(session, "cart", inquiry.snapshot["items"])

    async def test_other_chat_cannot_retry_bound_reference(self):
        session, inquiry, message = fixture()
        inquiry.telegram_chat_id = 456
        inquiry.telegram_connection_id = "connection"
        with patch.object(router, "send_inquiry", AsyncMock()) as send:
            await router._handle_business_message(session, message, 10)
            send.assert_not_awaited()

    async def test_sent_reference_never_resends_automatically(self):
        session, inquiry, message = fixture()
        inquiry.status = "sent"
        with patch.object(router, "send_inquiry", AsyncMock()) as send:
            await router._handle_business_message(session, message, 10)
            send.assert_not_awaited()

    async def test_stale_receipt_can_be_reclaimed_but_fresh_cannot(self):
        session, _, _ = fixture()
        receipt = SimpleNamespace(status="processing", received_at=utcnow()-timedelta(minutes=6))
        session.scalar.return_value = receipt
        self.assertTrue(await router._claim_update(session, 10))
        with self.assertRaises(HTTPException) as error:
            await router._claim_update(session, 10)
        self.assertEqual(error.exception.status_code, 503)
        receipt.status = "processed"
        self.assertFalse(await router._claim_update(session, 10))

    async def test_status_is_scoped_to_current_cart(self):
        session, inquiry, _ = fixture()
        session.scalar.return_value = None
        with patch.object(router, "_find_cart", AsyncMock(return_value=SimpleNamespace(id="cart-owner"))):
            with self.assertRaises(HTTPException) as error:
                await router.inquiry_status(REF, None, guest=True, session=session)
        self.assertEqual(error.exception.status_code, 404)
        query = session.scalar.call_args.args[0]
        self.assertIn("cart-owner", query.compile().params.values())

    async def test_retry_key_does_not_consume_quota_or_require_nonempty_cart(self):
        session, inquiry, _ = fixture()
        session.scalar.side_effect = [SimpleNamespace(id="cart"), inquiry]
        with patch.object(router, "_status", AsyncMock(return_value={"available": True})), \
             patch.object(router, "_find_cart", AsyncMock(return_value=SimpleNamespace(id="cart"))), \
             patch.object(router, "_limit_inquiry", AsyncMock()) as limit, \
             patch.object(router, "_cart_payload", AsyncMock()) as snapshot:
            result = await router.create_inquiry(router.InquiryRequest(locale="id"), None,
                guest=True, idempotency_key="existing-test-key", session=session)
        self.assertEqual(result["reference"], REF)
        self.assertIn(REF, result["message"])
        limit.assert_not_awaited()
        snapshot.assert_not_awaited()

    async def test_empty_cart_does_not_consume_inquiry_quota(self):
        session = SimpleNamespace(
            scalar=AsyncMock(side_effect=[SimpleNamespace(id="cart"), None]),
            commit=AsyncMock(),
        )
        with patch.object(router, "_status", AsyncMock(return_value={"available": True})), \
             patch.object(router, "_find_cart", AsyncMock(return_value=SimpleNamespace(id="cart"))), \
             patch.object(router, "_cart_payload", AsyncMock(return_value={"items": []})), \
             patch.object(router, "_limit_inquiry", AsyncMock()) as limit:
            with self.assertRaises(HTTPException) as error:
                await router.create_inquiry(router.InquiryRequest(locale="id"), None,
                    guest=True, idempotency_key="empty-cart-inquiry-key", session=session)
        self.assertEqual(error.exception.status_code, 400)
        self.assertEqual(error.exception.detail, {"error": "cart_empty"})
        limit.assert_not_awaited()

    async def test_cms_cannot_create_order_before_customer_message(self):
        session, inquiry, _ = fixture()
        inquiry.order_id = None
        with self.assertRaises(HTTPException) as error:
            await orders.create_manual_order(REF, None, user=None, session=session, idempotency_key=None)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(error.exception.detail["error"], "inquiry_not_received")

    async def test_missing_connection_is_fetched_before_processing(self):
        session, inquiry, message = fixture()
        connection = session.get.return_value
        session.get.side_effect = [None, connection]
        with patch.object(router, "bot_request", AsyncMock(return_value={"id": "connection"})) as api, \
             patch.object(router, "_store_connection", AsyncMock()) as store, \
             patch.object(router, "send_inquiry", AsyncMock()), \
             patch.object(router, "_remove_submitted_cart_quantities", AsyncMock()) as reconcile:
            await router._handle_business_message(session, message, 10)
        self.assertEqual(inquiry.status, "sent")
        reconcile.assert_awaited_once_with(session, "cart", [])
        api.assert_awaited_once()
        store.assert_awaited_once()

    async def test_single_and_eleven_photo_fallback(self):
        for count in (1, 2, 10, 11):
            calls = []
            async def api(token, method, payload):
                calls.append((method, payload))
                if method == "sendRichMessage":
                    raise delivery.TelegramDeliveryError("reject")
                if method == "sendPhoto":
                    self.assertIn("photo", payload)
                    self.assertNotIn("media", payload)
                return {"message_id": 1}
            snapshot = {"locale": "en", "subtotal": 100, "currency": "UZS", "item_count": count,
                "items": [{"name": "Product", "sku": "TEST", "variant": "", "quantity": 1,
                    "unit_price": 100, "line_total": 100, "image_url": "https://example.test/a.png"}] * count}
            with patch.object(delivery, "bot_request", api):
                self.assertEqual(await delivery.send_inquiry("test", "connection", 123, snapshot, REF), "album")
            self.assertEqual(sum(m == "sendPhoto" for m, _ in calls), int(count in (1, 11)))

if __name__ == "__main__":
    unittest.main()
