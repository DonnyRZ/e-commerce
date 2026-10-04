"""Regression coverage for non-blocking, durable order notifications."""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://unused:unused@127.0.0.1:1/audit"
)
os.environ.setdefault("JWT_SECRET", "isolated-test-secret-never-used-for-real-auth")

from routers import manual_orders
from routers.manual_orders import (
    TelegramDeliveryError,
    _dispatch_one_order_notification,
    _admin_order_payload,
    _queue_order_notification,
    _render_order_notification,
    _recover_stale_order_notifications,
    _telegram_target_for_order,
    update_manual_fulfillment,
)


class FakeResult:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return self.rows


class SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return False


def fulfillment_request(stage):
    import json
    body = json.dumps({"stage": stage}).encode()
    return Request({"type": "http", "headers": [(b"content-type", b"application/json")]}, receive=AsyncMock(return_value={"type": "http.request", "body": body}))


class OrderNotificationOutboxTests(unittest.IsolatedAsyncioTestCase):
    async def test_fulfillment_commits_stage_and_notification_together_without_telegram_wait(
        self,
    ):
        order = SimpleNamespace(
            id="order-1",
            order_number="MC-TEST-1",
            status="supplier_shipping",
            payment_state="paid",
            archived_at=None,
        )
        session = SimpleNamespace(
            scalar=AsyncMock(side_effect=[order, None, None]),
            add=Mock(),
            commit=AsyncMock(),
        )
        response_payload = {
            "order_number": order.order_number,
            "status": "received_by_admin",
            "telegram_notifications": [
                {"event_key": "fulfillment:received_by_admin", "status": "pending"}
            ],
        }
        added_rows = []
        session.add.side_effect = added_rows.append

        async def make_payload(_session, saved_order):
            self.assertEqual(saved_order.status, "received_by_admin")
            return response_payload

        with (
            patch.object(manual_orders, "audit", new_callable=AsyncMock),
            patch.object(
                manual_orders,
                "_admin_order_payload",
                new_callable=AsyncMock,
                side_effect=make_payload,
            ),
            patch.object(manual_orders, "bot_request", new_callable=AsyncMock) as send,
        ):
            result = await update_manual_fulfillment(
                "MC-TEST-1",
                fulfillment_request("received_by_admin"),
                SimpleNamespace(id="admin-1"),
                session,
                None,
            )

        self.assertEqual(result["status"], "received_by_admin")
        self.assertEqual(order.status, "received_by_admin")
        self.assertEqual(session.commit.await_count, 1)
        self.assertEqual(len(added_rows), 2)
        stage, notification = added_rows
        self.assertEqual(stage.stage, "received_by_admin")
        self.assertEqual(stage.status, "completed")
        self.assertEqual(notification.event_key, "fulfillment:received_by_admin")
        self.assertEqual(notification.status, "pending")
        send.assert_not_awaited()

    async def test_repeated_or_stale_transition_is_rejected_without_duplicate_notification(
        self,
    ):
        order = SimpleNamespace(
            id="order-1",
            order_number="MC-TEST-2",
            status="received_by_admin",
            payment_state="paid",
            archived_at=None,
        )
        session = SimpleNamespace(
            scalar=AsyncMock(return_value=order),
            add=Mock(),
            commit=AsyncMock(),
        )

        with self.assertRaises(HTTPException) as caught:
            await update_manual_fulfillment(
                "MC-TEST-2",
                fulfillment_request("received_by_admin"),
                SimpleNamespace(id="admin-1"),
                session,
                None,
            )

        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(
            caught.exception.detail["error"], "invalid_fulfillment_transition"
        )
        session.add.assert_not_called()
        session.commit.assert_not_awaited()

    async def test_queue_deduplicates_the_same_transition_event(self):
        existing = SimpleNamespace(event_key="fulfillment:received_by_admin")
        session = SimpleNamespace(scalar=AsyncMock(return_value=existing), add=Mock())

        result = await _queue_order_notification(
            "order-1", "fulfillment:received_by_admin", "received", session
        )

        self.assertIs(result, existing)
        session.add.assert_not_called()

    async def test_order_event_is_rendered_in_active_locale_and_keeps_admin_reason(self):
        order = SimpleNamespace(order_number="MC-TEST-LOCALE")
        rejected = SimpleNamespace(
            event_key="payment_rejected:evidence-1:digest",
            event_type="payment_rejected",
            event_payload={"reason": "Please send a clearer receipt."},
            message_text="Indonesian preview",
        )
        rendered = _render_order_notification(rejected, order, "ru")
        self.assertIn("заказа MC-TEST-LOCALE", rendered)
        self.assertIn("Причина: Please send a clearer receipt.", rendered)

        fulfillment = SimpleNamespace(
            event_key="fulfillment:delivered",
            event_type="fulfillment",
            event_payload={"stage": "delivered"},
            message_text="Indonesian preview",
        )
        expected = {
            "id": "Update order MC-TEST-LOCALE: Barang diterima customer.",
            "en": "Order MC-TEST-LOCALE update: The item has been delivered to you.",
            "uz": "MC-TEST-LOCALE buyurtma yangilanishi: Mahsulot sizga yetkazildi.",
            "ru": "Обновление по заказу MC-TEST-LOCALE: Товар доставлен.",
        }
        for locale, expected_text in expected.items():
            with self.subTest(locale=locale):
                self.assertEqual(
                    _render_order_notification(fulfillment, order, locale),
                    expected_text,
                )

    async def test_web_order_target_uses_the_latest_conversation_locale(self):
        inquiry = SimpleNamespace(
            order_id="order-1",
            telegram_connection_id="connection-1",
            telegram_chat_id=123,
            locale="uz",
        )
        conversation = SimpleNamespace(locale="ru")
        session = SimpleNamespace(
            scalar=AsyncMock(side_effect=[inquiry, conversation])
        )

        target = await _telegram_target_for_order(session, "order-1")

        self.assertEqual(target, ("connection-1", 123, "ru"))

    async def test_order_detail_exposes_notification_state_for_progress_reconciliation(
        self,
    ):
        notification = SimpleNamespace(
            event_key="fulfillment:received_by_admin",
            status="pending",
            error_code=None,
            message_id=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        stage = SimpleNamespace(
            stage="received_by_admin",
            status="completed",
            carrier=None,
            tracking_number=None,
            shipped_at=None,
            received_at=datetime.now(timezone.utc),
            expected_at=None,
            note=None,
            shipping_document_key=None,
        )
        order = SimpleNamespace(
            id="order-1",
            order_number="MC-TEST-3",
            created_at=datetime.now(timezone.utc),
            status="received_by_admin",
            archived_at=None,
            payment_state="paid",
            order_source="telegram_manual",
            fulfillment_mode="pre_order",
            preorder_estimate_days=21,
            grand_total=100,
            currency="UZS",
            subtotal=100,
            shipping_amount=0,
            shipping_method="manual",
            guest_email=None,
            user_id=None,
            shipping_address={},
        )
        session = SimpleNamespace(
            execute=AsyncMock(
                side_effect=[
                    FakeResult(),
                    FakeResult([stage]),
                    FakeResult([notification]),
                    FakeResult(),
                ]
            ),
            scalar=AsyncMock(return_value=None),
        )

        payload = await _admin_order_payload(session, order)

        self.assertEqual(payload["status"], "received_by_admin")
        self.assertEqual(
            payload["fulfillment"][0]["telegram_notification"]["status"], "pending"
        )
        self.assertEqual(
            payload["telegram_notifications"][0]["event_key"],
            "fulfillment:received_by_admin",
        )

    async def test_dispatch_marks_success_only_after_telegram_accepts_message(self):
        notification = SimpleNamespace(
            id="notification-1",
            order_id="order-1",
            event_key="fulfillment:received_by_admin",
            event_type="fulfillment",
            event_payload={"stage": "received_by_admin"},
            message_text="Barang diterima admin",
            status="pending",
            claimed_at=None,
            completed_at=None,
            error_code=None,
            message_id=None,
        )
        session = SimpleNamespace(
            scalar=AsyncMock(return_value=notification),
            get=AsyncMock(
                return_value=SimpleNamespace(id="order-1", order_number="MC-TEST-1")
            ),
            commit=AsyncMock(),
        )

        async def send_message(_token, _method, payload):
            self.assertEqual(notification.status, "sending")
            self.assertEqual(
                payload["text"],
                "MC-TEST-1 buyurtma yangilanishi: Mahsulot admin tomonidan qabul qilindi.",
            )
            return {"message_id": 101}

        with (
            patch.object(
                manual_orders,
                "SessionLocal",
                side_effect=lambda: SessionContext(session),
            ),
            patch.object(
                manual_orders,
                "_telegram_target_for_order",
                new_callable=AsyncMock,
                return_value=("connection-1", "chat-1", "uz"),
            ),
            patch.object(manual_orders, "TELEGRAM_BOT_TOKEN", "test-token"),
            patch.object(
                manual_orders,
                "bot_request",
                new_callable=AsyncMock,
                side_effect=send_message,
            ) as send,
            patch.object(
                manual_orders, "record_outgoing_message", new_callable=AsyncMock
            ) as record,
        ):
            dispatched = await _dispatch_one_order_notification()

        self.assertTrue(dispatched)
        self.assertEqual(notification.status, "sent")
        self.assertEqual(notification.message_id, 101)
        self.assertIsNotNone(notification.completed_at)
        send.assert_awaited_once()
        record.assert_awaited_once()

    async def test_definite_rejection_is_failed_but_timeout_is_unknown_and_never_auto_retried(
        self,
    ):
        for error, expected_status in (
            (
                TelegramDeliveryError(
                    "rejected", safe_code="telegram_api_rejected_request"
                ),
                "failed",
            ),
            (TimeoutError("delivery outcome unknown"), "unknown"),
        ):
            with self.subTest(expected_status=expected_status):
                notification = SimpleNamespace(
                    id=f"notification-{expected_status}",
                    order_id="order-1",
                    event_key="fulfillment:received_by_admin",
                    message_text="Barang diterima admin",
                    status="pending",
                    claimed_at=None,
                    completed_at=None,
                    error_code=None,
                    message_id=None,
                )
                session = SimpleNamespace(
                    scalar=AsyncMock(side_effect=[notification, None]),
                    get=AsyncMock(return_value=SimpleNamespace(id="order-1")),
                    commit=AsyncMock(),
                )
                with (
                    patch.object(
                        manual_orders,
                        "SessionLocal",
                        side_effect=lambda: SessionContext(session),
                    ),
                    patch.object(
                        manual_orders,
                        "_telegram_target_for_order",
                        new_callable=AsyncMock,
                        return_value=("connection-1", "chat-1", "id"),
                    ),
                    patch.object(manual_orders, "TELEGRAM_BOT_TOKEN", "test-token"),
                    patch.object(
                        manual_orders,
                        "bot_request",
                        new_callable=AsyncMock,
                        side_effect=error,
                    ) as send,
                    patch.object(manual_orders.order_notification_logger, "exception"),
                ):
                    self.assertTrue(await _dispatch_one_order_notification())
                    self.assertEqual(notification.status, expected_status)
                    self.assertFalse(await _dispatch_one_order_notification())

                send.assert_awaited_once()

    async def test_stale_in_flight_send_becomes_unknown_instead_of_being_retried(self):
        stale = SimpleNamespace(
            status="sending",
            claimed_at=datetime.now(timezone.utc) - timedelta(minutes=3),
            completed_at=None,
            error_code=None,
        )
        session = SimpleNamespace(execute=AsyncMock(return_value=FakeResult([stale])))

        await _recover_stale_order_notifications(session)

        self.assertEqual(stale.status, "unknown")
        self.assertEqual(stale.error_code, "delivery_outcome_unknown")
        self.assertIsNotNone(stale.completed_at)


if __name__ == "__main__":
    unittest.main()
