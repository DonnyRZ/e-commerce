"""Isolated safety checks for Telegram Inbox behavior."""

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://unused:unused@127.0.0.1:1/audit")
os.environ.setdefault("JWT_SECRET", "isolated-test-secret-never-used-for-real-auth")

import routers.telegram as telegram_router
import telegram_inbox_service as inbox
from db.models import utcnow


class TelegramInboxTests(unittest.IsolatedAsyncioTestCase):
    async def test_language_and_candidate_keyboard_are_localized(self):
        self.assertEqual(inbox.locale_from_language("uz-Latn"), "uz")
        self.assertEqual(inbox.locale_from_language("fr"), "id")
        markup = inbox.candidate_keyboard("abcdefghijklmnop", "ru")
        buttons = markup["inline_keyboard"][0]
        self.assertEqual(buttons[0]["text"], "Да, верно")
        self.assertEqual(buttons[1]["callback_data"], "CAT:abcdefghijklmnop:no")
        self.assertLessEqual(len(buttons[1]["callback_data"].encode()), 64)

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
