"""Isolated safety checks for Telegram Inbox behavior."""

import os
import sys
import unittest
from datetime import timedelta
from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from alembic.migration import MigrationContext
from alembic.operations import Operations

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://unused:unused@127.0.0.1:1/audit")
os.environ.setdefault("JWT_SECRET", "isolated-test-secret-never-used-for-real-auth")

import routers.telegram as telegram_router
import routers.telegram_inbox as telegram_inbox_router
import telegram_inbox_service as inbox
import telegram_inquiries
from routers.telegram_inbox import _message_payload, _reconstructed_cart_message
from db.models import utcnow


class TelegramInboxTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_web_inquiry_sets_the_conversation_locale_for_future_replies(self):
        reference = f"SC-{'A' * 32}"
        connection = SimpleNamespace(
            connection_id="bc-1",
            username=telegram_router._normalized_username(
                telegram_router.TELEGRAM_STORE_USERNAME
            ),
            is_enabled=True,
            can_reply=True,
            can_read_messages=True,
            business_user_id="999",
        )
        inquiry = SimpleNamespace(
            reference=reference,
            locale="ru",
            status="pending",
            expires_at=utcnow() + timedelta(days=1),
            snapshot={"items": []},
            telegram_chat_id=None,
            telegram_connection_id=None,
            cart_id="cart-1",
        )
        conversation = SimpleNamespace(
            locale="uz", locale_source="direct_default", updated_at=utcnow()
        )
        session = SimpleNamespace(
            get=AsyncMock(return_value=connection),
            scalar=AsyncMock(side_effect=[inquiry, conversation, None]),
            commit=AsyncMock(),
        )
        message = {
            "business_connection_id": "bc-1",
            "chat": {"type": "private", "id": 123},
            "from": {"id": 123},
            "text": reference,
        }

        with patch.object(telegram_router, "TELEGRAM_BOT_TOKEN", "fake-token"), patch.object(
            telegram_router, "send_inquiry", new_callable=AsyncMock, return_value="rich"
        ):
            await telegram_router._handle_business_message(session, message, 55)

        self.assertEqual((conversation.locale, conversation.locale_source), ("ru", "web"))
        self.assertEqual(inquiry.status, "sent")
        self.assertEqual(inquiry.telegram_chat_id, 123)

    async def test_rich_message_schema_migration_compiles_in_both_directions(self):
        migration_path = (
            Path(__file__).resolve().parents[1]
            / "alembic"
            / "versions"
            / "v1w2x3y4z5a_telegram_inbox_rich_messages.py"
        )
        spec = spec_from_file_location("telegram_rich_migration_test", migration_path)
        migration = module_from_spec(spec)
        spec.loader.exec_module(migration)

        def render(operation):
            output = StringIO()
            context = MigrationContext.configure(
                dialect_name="postgresql",
                opts={"as_sql": True, "output_buffer": output},
            )
            with Operations.context(context):
                operation()
            return output.getvalue()

        upgrade_sql = render(migration.upgrade)
        downgrade_sql = render(migration.downgrade)
        self.assertIn("ADD COLUMN rich_content JSONB", upgrade_sql)
        self.assertIn("ADD COLUMN media_group_id VARCHAR(255)", upgrade_sql)
        self.assertIn("DROP COLUMN media_group_id", downgrade_sql)
        self.assertIn("DROP COLUMN rich_content", downgrade_sql)

    async def test_locale_and_notification_migration_backfills_legacy_rows(self):
        migration_path = (
            Path(__file__).resolve().parents[1]
            / "alembic"
            / "versions"
            / "x3y4z5a6b7c_telegram_locale_and_typed_notifications.py"
        )
        spec = spec_from_file_location("telegram_locale_migration_test", migration_path)
        migration = module_from_spec(spec)
        spec.loader.exec_module(migration)

        def render(operation):
            output = StringIO()
            context = MigrationContext.configure(
                dialect_name="postgresql",
                opts={"as_sql": True, "output_buffer": output},
            )
            with Operations.context(context):
                operation()
            return output.getvalue()

        upgrade_sql = render(migration.upgrade)
        downgrade_sql = render(migration.downgrade)
        self.assertIn("locale_source VARCHAR(20) DEFAULT 'legacy' NOT NULL", upgrade_sql)
        self.assertIn("event_type = CASE", upgrade_sql)
        self.assertIn("jsonb_build_object", upgrade_sql)
        self.assertIn("DROP COLUMN locale_source", downgrade_sql)
        self.assertIn("DROP COLUMN event_payload", downgrade_sql)

    async def test_rich_cart_message_normalizes_slides_without_html_or_file_ids(self):
        telegram_message = {
            "rich_message": {
                "blocks": [
                    {"type": "heading", "text": "Cart request"},
                    {"type": "paragraph", "text": ["SC-", {"type": "bold", "text": "A" * 32}]},
                    {
                        "type": "slideshow",
                        "blocks": [
                            {
                                "type": "photo",
                                "photo": [
                                    {"file_id": "small-secret-file-id", "file_size": 100},
                                    {"file_id": "large-secret-file-id", "file_size": 900},
                                ],
                                "caption": {"text": [{"type": "bold", "text": "Product"}, "\nQty: 2"]},
                            }
                        ],
                    },
                    {"type": "footer", "text": "Subtotal: 20,000 UZS"},
                ]
            }
        }

        stored = inbox.normalize_rich_content(telegram_message)
        self.assertEqual(stored["title"], "Cart request")
        self.assertEqual(stored["intro"], f"SC-{'A' * 32}")
        self.assertEqual(stored["slides"][0]["caption"], "Product\nQty: 2")
        self.assertEqual(stored["slides"][0]["photo_file_id"], "large-secret-file-id")
        self.assertEqual(stored["footer"], ["Subtotal: 20,000 UZS"])

        row = SimpleNamespace(
            id="message-1", telegram_message_id=41, direction="outbound", source="telegram",
            message_type="rich", text="", rich_content=stored, media_group_id=None,
            photo_file_id=None, deleted_at=None, created_at=utcnow(), edited_at=None,
        )
        payload = _message_payload(row)
        self.assertEqual(payload["type"], "rich")
        self.assertEqual(payload["rich_content"]["slides"][0]["image_url"],
                         "/api/v1/admin/telegram-inbox/media/message-1?media_index=0")
        self.assertNotIn("large-secret-file-id", repr(payload))
        self.assertNotIn("small-secret-file-id", repr(payload))

    async def test_historical_cart_reconstruction_is_explicitly_labeled(self):
        reference = f"SC-{'B' * 32}"
        inquiry = SimpleNamespace(
            id="inquiry-1", reference=reference, delivered_at=utcnow(),
            snapshot={
                "locale": "id", "subtotal": 1000, "currency": "UZS",
                "items": [{"name": "Produk", "quantity": 1, "unit_price": 1000,
                           "line_total": 1000, "image_url": "https://cdn.test/product.jpg"}],
            },
        )
        message = _reconstructed_cart_message(inquiry)
        self.assertTrue(message["is_reconstructed"])
        self.assertEqual(message["source"], "snapshot")
        self.assertEqual(message["rich_content"]["slides"][0]["image_url"],
                         "https://cdn.test/product.jpg")

    async def test_rich_send_records_telegram_message_result(self):
        recorded = []
        snapshot = {
            "locale": "id", "subtotal": 1000, "currency": "UZS", "items": [],
        }
        sent = {
            "message_id": 501,
            "date": int(utcnow().timestamp()),
            "rich_message": {"blocks": [{"type": "heading", "text": "Cart"}]},
        }

        async def fake_bot_request(_token, method, _payload):
            self.assertEqual(method, "sendRichMessage")
            return sent

        async def record(message):
            recorded.append(message)

        with patch.object(telegram_inquiries, "bot_request", fake_bot_request):
            result = await telegram_inquiries.send_inquiry(
                "token", "connection", 123, snapshot, f"SC-{'C' * 32}", on_message=record
            )
        self.assertEqual(result, "rich")
        self.assertEqual(recorded, [sent])

    async def test_successful_fallback_records_album_and_summary_messages(self):
        snapshot = {
            "locale": "id", "subtotal": 1000, "currency": "UZS",
            "items": [
                {"name": "One", "quantity": 1, "unit_price": 500, "line_total": 500,
                 "sku": "ONE", "variant": "", "availability": "pre_order",
                 "image_url": "https://cdn.test/one.jpg"},
                {"name": "Two", "quantity": 1, "unit_price": 500, "line_total": 500,
                 "sku": "TWO", "variant": "", "availability": "pre_order",
                 "image_url": "https://cdn.test/two.jpg"},
            ],
        }
        recorded = []

        async def fake_bot_request(_token, method, _payload):
            if method == "sendRichMessage":
                raise telegram_inquiries.TelegramDeliveryError("rich not supported")
            if method == "sendMediaGroup":
                return [
                    {"message_id": 701, "media_group_id": "album-2", "photo": [{"file_id": "p1"}]},
                    {"message_id": 702, "media_group_id": "album-2", "photo": [{"file_id": "p2"}]},
                ]
            if method == "sendMessage":
                return {"message_id": 703, "text": "Cart summary"}
            raise AssertionError(f"Unexpected Telegram method {method}")

        async def record(message):
            recorded.append(message)

        with patch.object(telegram_inquiries, "bot_request", fake_bot_request):
            result = await telegram_inquiries.send_inquiry(
                "token", "connection", 123, snapshot, f"SC-{'E' * 32}", on_message=record
            )
        self.assertEqual(result, "album")
        self.assertEqual([message["message_id"] for message in recorded], [701, 702, 703])
        self.assertEqual(recorded[0]["media_group_id"], "album-2")
        self.assertEqual(recorded[2]["text"], "Cart summary")

    async def test_album_fallback_records_each_message_and_partial_rejection_is_unknown(self):
        snapshot = {
            "locale": "id", "subtotal": 1000, "currency": "UZS",
            "items": [
                {"name": "One", "quantity": 1, "unit_price": 500, "line_total": 500,
                 "sku": "ONE", "variant": "", "availability": "pre_order",
                 "image_url": "https://cdn.test/one.jpg"},
                {"name": "Two", "quantity": 1, "unit_price": 500, "line_total": 500,
                 "sku": "TWO", "variant": "", "availability": "pre_order",
                 "image_url": "https://cdn.test/two.jpg"},
            ],
        }
        recorded = []
        calls = []

        async def fake_bot_request(_token, method, _payload):
            calls.append(method)
            if method == "sendRichMessage" or method == "sendMessage":
                raise telegram_inquiries.TelegramDeliveryError("rejected")
            return [
                {"message_id": 601, "media_group_id": "album-1", "photo": [{"file_id": "p1"}]},
                {"message_id": 602, "media_group_id": "album-1", "photo": [{"file_id": "p2"}]},
            ]

        async def record(message):
            recorded.append(message)

        with patch.object(telegram_inquiries, "bot_request", fake_bot_request):
            with self.assertRaises(telegram_inquiries.TelegramPartialDeliveryError):
                await telegram_inquiries.send_inquiry(
                    "token", "connection", 123, snapshot, f"SC-{'D' * 32}", on_message=record
                )
        self.assertEqual(calls, ["sendRichMessage", "sendMediaGroup", "sendMessage"])
        self.assertEqual([message["message_id"] for message in recorded], [601, 602])

    async def test_language_and_candidate_keyboard_are_localized(self):
        self.assertEqual(inbox.locale_from_language("uz-Latn"), "uz")
        self.assertEqual(inbox.locale_from_language("fr"), "id")
        markup = inbox.candidate_keyboard("abcdefghijklmnop", "ru")
        buttons = markup["inline_keyboard"][0]
        self.assertEqual(buttons[0]["text"], "Да, верно")
        self.assertEqual(buttons[1]["callback_data"], "CAT:abcdefghijklmnop:no")
        self.assertLessEqual(len(buttons[1]["callback_data"].encode()), 64)
        self.assertEqual(
            inbox.candidate_callback_error("uz", "invalid"),
            "Bu tanlov noto‘g‘ri yoki muddati tugagan.",
        )
        for locale in ("id", "en", "uz", "ru"):
            with self.subTest(locale=locale):
                self.assertTrue(inbox.candidate_callback_error(locale, "inactive"))

    async def test_locale_sources_follow_web_direct_and_admin_precedence(self):
        conversation = SimpleNamespace(locale="ru", locale_source="web")
        self.assertEqual(inbox.apply_direct_default_locale(conversation), "uz")
        self.assertEqual(conversation.locale_source, "direct_default")

        conversation.locale = "ru"
        conversation.locale_source = "admin"
        self.assertEqual(inbox.apply_direct_default_locale(conversation), "ru")
        self.assertEqual(conversation.locale_source, "admin")

        inbox.apply_web_locale(conversation, "en")
        self.assertEqual((conversation.locale, conversation.locale_source), ("en", "web"))

    async def test_admin_locale_selector_marks_the_locale_as_an_override(self):
        conversation = SimpleNamespace(
            id="conversation-1", locale="uz", locale_source="direct_default"
        )
        session = SimpleNamespace(
            scalar=AsyncMock(return_value=conversation), commit=AsyncMock()
        )
        with (
            patch.object(telegram_inbox_router, "audit", new_callable=AsyncMock),
            patch.object(
                telegram_inbox_router,
                "_conversation_order_context",
                new_callable=AsyncMock,
                return_value=("inquiry", 0, None, []),
            ),
            patch.object(telegram_inbox_router, "_conversation_payload", return_value={}),
        ):
            await telegram_inbox_router.update_conversation(
                "conversation-1",
                telegram_inbox_router.ConversationUpdateIn(locale="ru"),
                SimpleNamespace(id="admin-1"),
                session,
                None,
            )
        self.assertEqual((conversation.locale, conversation.locale_source), ("ru", "admin"))

    async def test_business_message_edit_updates_existing_transcript_row(self):
        connection = SimpleNamespace(
            connection_id="bc-1",
            username=inbox.TELEGRAM_STORE_USERNAME.casefold().lstrip("@"),
            is_enabled=True,
            can_read_messages=True,
            business_user_id="999",
        )
        conversation = SimpleNamespace(
            id="conversation-1", connection_id="bc-1", chat_id=123,
            customer_user_id="123", customer_username="", customer_name="Customer",
            telegram_language_code="en", locale="en", status="needs_admin",
            last_message_at=utcnow(), last_customer_message_at=utcnow(),
            last_admin_message_at=None, updated_at=utcnow(),
        )
        transcript = SimpleNamespace(
            conversation_id="conversation-1", text="Old text", message_type="text",
            photo_file_id=None, photo_file_unique_id=None, photo_file_size=None,
            deleted_at=None, edited_at=None,
        )
        session = SimpleNamespace(
            get=AsyncMock(return_value=connection),
            scalar=AsyncMock(side_effect=[conversation, transcript]),
            flush=AsyncMock(),
        )
        message = {
            "business_connection_id": "bc-1",
            "message_id": 77,
            "date": int(utcnow().timestamp()),
            "chat": {"type": "private", "id": 123},
            "from": {"id": 123, "first_name": "Customer", "language_code": "en"},
            "text": "Updated text",
        }
        row = await inbox.persist_business_message(session, message, 201, edited=True)
        self.assertIs(row, transcript)
        self.assertEqual(row.text, "Updated text")
        self.assertEqual(row.update_id, 201)
        self.assertIsNotNone(row.edited_at)

    async def test_rich_message_redelivery_updates_the_same_transcript_row(self):
        connection = SimpleNamespace(
            connection_id="bc-1",
            username=inbox.TELEGRAM_STORE_USERNAME.casefold().lstrip("@"),
            is_enabled=True,
            can_read_messages=True,
            business_user_id="999",
        )
        conversation = SimpleNamespace(
            id="conversation-1", connection_id="bc-1", chat_id=123,
            customer_user_id="123", customer_username="", customer_name="Customer",
            telegram_language_code="en", locale="en", status="needs_admin",
            last_message_at=utcnow(), last_customer_message_at=utcnow(),
            last_admin_message_at=None, updated_at=utcnow(),
        )
        transcript = SimpleNamespace(
            conversation_id="conversation-1", text="", message_type="rich",
            rich_content=None, media_group_id=None, photo_file_id=None,
            photo_file_unique_id=None, photo_file_size=None, deleted_at=None, edited_at=None,
            direction="outbound",
        )
        session = SimpleNamespace(
            get=AsyncMock(return_value=connection),
            scalar=AsyncMock(side_effect=[conversation, transcript, conversation, transcript]),
            flush=AsyncMock(),
        )
        message = {
            "business_connection_id": "bc-1", "message_id": 78,
            "date": int(utcnow().timestamp()), "chat": {"type": "private", "id": 123},
            "from": {"id": 999, "is_bot": True},
            "rich_message": {
                "blocks": [
                    {"type": "heading", "text": "Cart"},
                    {"type": "slideshow", "blocks": [
                        {"type": "photo", "photo": [{"file_id": "private-file"}],
                         "caption": {"text": "Product"}},
                    ]},
                ]
            },
        }

        first = await inbox.persist_business_message(session, message, None)
        second = await inbox.persist_business_message(session, message, 202)
        self.assertIs(first, transcript)
        self.assertIs(second, transcript)
        self.assertEqual(transcript.direction, "outbound")
        self.assertEqual(transcript.message_type, "rich")
        self.assertEqual(transcript.rich_content["slides"][0]["caption"], "Product")
        self.assertEqual(transcript.rich_content["slides"][0]["photo_file_id"], "private-file")
        self.assertEqual(transcript.update_id, 202)

    async def test_outgoing_rich_api_result_is_mirrored_with_its_telegram_payload(self):
        session = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(business_user_id="999")))
        sent_message = {
            "message_id": 501,
            "date": int(utcnow().timestamp()),
            "chat": {"type": "private", "id": 123},
            "rich_message": {"blocks": [{"type": "heading", "text": "Cart"}]},
        }
        with patch.object(inbox, "capture_business_message", AsyncMock()) as capture:
            await inbox.record_outgoing_message(
                session, "bc-1", 123, sent_message, "", source_override="telegram"
            )
        payload = capture.await_args.args[1]
        self.assertEqual(payload["message_id"], 501)
        self.assertEqual(payload["business_connection_id"], "bc-1")
        self.assertEqual(payload["rich_message"]["blocks"][0]["text"], "Cart")
        self.assertEqual(capture.await_args.kwargs["source_override"], "telegram")
        self.assertTrue(capture.await_args.kwargs["allow_outgoing_without_read"])

    async def test_outgoing_api_message_is_stored_even_without_read_messages_right(self):
        connection = SimpleNamespace(
            connection_id="bc-1",
            username=inbox.TELEGRAM_STORE_USERNAME.casefold().lstrip("@"),
            is_enabled=True,
            can_read_messages=False,
            business_user_id="999",
        )
        conversation = SimpleNamespace(
            id="conversation-1", connection_id="bc-1", chat_id=123,
            customer_user_id="123", customer_username="", customer_name="Customer",
            telegram_language_code="", locale="id", status="waiting_customer",
            last_message_at=utcnow(), last_customer_message_at=None,
            last_admin_message_at=utcnow(), updated_at=utcnow(),
        )
        session = SimpleNamespace(
            get=AsyncMock(return_value=connection),
            scalar=AsyncMock(side_effect=[conversation, None]),
            add=Mock(),
            flush=AsyncMock(),
        )
        message = {
            "business_connection_id": "bc-1", "message_id": 901,
            "date": int(utcnow().timestamp()), "chat": {"type": "private", "id": 123},
            "from": {"id": 999, "is_bot": True}, "text": "Sent from CMS",
        }
        row = await inbox.persist_business_message(
            session, message, None, allow_outgoing_without_read=True
        )
        self.assertIsNotNone(row)
        self.assertEqual(row.direction, "outbound")
        self.assertEqual(row.text, "Sent from CMS")

    async def test_candidate_callback_is_bound_to_its_business_chat(self):
        now = utcnow()
        candidate = SimpleNamespace(
            id="candidate-1", conversation_id="conversation-1", status="pending",
            created_at=now, confirmation_message_id=77,
            confirmation_source=None, confirmed_at=None,
        )
        conversation = SimpleNamespace(
            id="conversation-1", connection_id="bc-1", chat_id=123,
            status="waiting_customer", last_customer_message_at=now,
            last_message_at=now, locale="id",
        )
        connection = SimpleNamespace(is_enabled=True, can_reply=True, can_read_messages=True)
        session = SimpleNamespace(
            scalar=AsyncMock(return_value=candidate),
            get=AsyncMock(side_effect=[conversation, connection]),
            commit=AsyncMock(),
        )
        callback = {
            "id": "callback-1",
            "data": "CAT:abcdefghijklmnop:yes",
            "from": {"id": 123},
            "message": {
                "business_connection_id": "bc-1",
                "message_id": 77,
                "chat": {"type": "private", "id": 123},
                "photo": [{"file_id": "photo"}],
            },
        }
        with patch.object(telegram_router, "TELEGRAM_BOT_TOKEN", "fake-token"), \
             patch.object(telegram_router, "_answer_payment_callback", AsyncMock()) as answer, \
             patch.object(telegram_router, "bot_request", AsyncMock()) as bot:
            handled = await telegram_router._handle_product_candidate_callback(session, callback)
        self.assertTrue(handled)
        self.assertEqual(candidate.status, "confirmed")
        self.assertEqual(candidate.confirmation_source, "customer")
        self.assertEqual(conversation.status, "ready_for_order")
        self.assertGreaterEqual(conversation.last_customer_message_at, now)
        answer.assert_awaited_once()
        self.assertEqual(bot.await_args.args[1], "editMessageCaption")

    async def test_candidate_callback_from_another_chat_is_rejected(self):
        candidate = SimpleNamespace(
            id="candidate-1", conversation_id="conversation-1", status="pending",
            created_at=utcnow(), confirmation_message_id=77,
        )
        conversation = SimpleNamespace(id="conversation-1", connection_id="bc-1", chat_id=123)
        connection = SimpleNamespace(is_enabled=True, can_reply=True, can_read_messages=True)
        session = SimpleNamespace(
            scalar=AsyncMock(return_value=candidate),
            get=AsyncMock(side_effect=[conversation, connection]),
            commit=AsyncMock(),
        )
        callback = {
            "id": "callback-1", "data": "CAT:abcdefghijklmnop:no",
            "from": {"id": 456},
            "message": {
                "business_connection_id": "bc-1", "message_id": 77,
                "chat": {"type": "private", "id": 123},
            },
        }
        with patch.object(telegram_router, "_answer_payment_callback", AsyncMock()) as answer:
            handled = await telegram_router._handle_product_candidate_callback(session, callback)
        self.assertTrue(handled)
        self.assertEqual(candidate.status, "pending")
        session.commit.assert_not_awaited()
        self.assertTrue(answer.await_args.kwargs["show_alert"])


if __name__ == "__main__":
    unittest.main()
