import asyncio
from types import SimpleNamespace

import pytest

import routers.telegram as telegram_router
from payment_destinations import (
    destination_admin_payload,
    mask_account_number,
    normalize_account_number,
    payment_choice_keyboard,
    payment_detail_keyboard,
    payment_detail_text,
    payment_prompt_text,
)
from telegram_inquiries import telegram_webhook_is_ready


def _destination(**overrides):
    values = {
        "id": "destination-1",
        "slot": 0,
        "callback_key": "a1b2c3d4",
        "bank_name": "Kapitalbank",
        "destination_type": "card",
        "account_number": "8600120102769961",
        "holder_name": "Test Customer",
        "is_active": True,
        "created_at": None,
        "updated_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_destination_number_is_normalized_and_type_validated():
    assert normalize_account_number("8600 1201-0276 9961", "card") == "8600120102769961"
    assert normalize_account_number("2020 8000 1234 5678 9001", "bank_account") == "20208000123456789001"
    with pytest.raises(ValueError, match="invalid_card_number_length"):
        normalize_account_number("1234", "card")
    with pytest.raises(ValueError, match="account_number_digits_only"):
        normalize_account_number("8600-ABCD-1234", "card")


def test_admin_list_masks_account_number_but_editor_can_request_full_value():
    row = _destination()
    assert destination_admin_payload(row)["masked_account_number"] == "•••• 9961"
    assert "account_number" not in destination_admin_payload(row)
    assert destination_admin_payload(row, include_number=True)["account_number"] == row.account_number
    assert mask_account_number("") == "—"


def test_keyboard_uses_one_inline_choice_per_bank_and_short_callback_data():
    rows = [_destination(), _destination(slot=1, callback_key="e5f6a7b8", bank_name="NBU")]
    keyboard = payment_choice_keyboard(rows, "abcdefghijklmnop", "id")
    assert len(keyboard["inline_keyboard"]) == 2
    assert keyboard["inline_keyboard"][0][0]["text"] == "Kapitalbank ···· 9961"
    assert all(len(row[0]["callback_data"].encode()) <= 64 for row in keyboard["inline_keyboard"])
    detail_keyboard = payment_detail_keyboard(
        {"account_number": "8600120102769961"}, "abcdefghijklmnop", "id"
    )
    assert detail_keyboard["inline_keyboard"][0][0]["copy_text"]["text"] == "8600120102769961"
    assert detail_keyboard["inline_keyboard"][1][0]["callback_data"] == "back:abcdefghijklmnop:id"


def test_payment_message_is_localized_and_contains_the_exact_order_total():
    order = SimpleNamespace(order_number="MC-123", grand_total=125000, currency="UZS")
    text = payment_prompt_text(order, 3, "id", "https://shop.example.test/orders/MC-123")
    assert "MC-123" in text
    assert "125 000 UZS" in text
    assert "Pilih bank" in text
    destination = {
        "bank_name": "Kapitalbank",
        "destination_type": "card",
        "account_number": "8600120102769961",
        "holder_name": "Test Customer",
    }
    details = payment_detail_text(order, destination, "id")
    assert "8600120102769961" in details
    assert "125 000 UZS" in details
    assert "kirim bukti pembayaran" in details


def test_payment_callback_selection_is_bound_to_original_business_chat(monkeypatch):
    token = "abcdefghijklmnop"
    payment = SimpleNamespace(
        telegram_selection_token=token,
        telegram_payment_message_id=700,
        order_id="order-id",
        status="pending",
        destination_id=None,
        destination_snapshot=None,
    )
    order = SimpleNamespace(
        id="order-id",
        order_number="MC-123",
        grand_total=125000,
        currency="UZS",
        status="pending_payment",
    )
    inquiry = SimpleNamespace(
        order_id="order-id",
        telegram_connection_id="business-connection",
        telegram_chat_id=12345,
        locale="id",
    )
    destination = _destination()
    calls = []

    class Session:
        values = [payment, order, inquiry, destination]

        async def scalar(self, _query):
            return self.values.pop(0)

        async def commit(self):
            return None

    async def fake_bot_request(_token, method, payload):
        calls.append((method, payload))
        return {}

    monkeypatch.setattr(telegram_router, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(telegram_router, "bot_request", fake_bot_request)
    callback = {
        "id": "callback-id",
        "data": f"bank:{token}:{destination.callback_key}",
        "from": {"id": 12345},
        "message": {
            "message_id": 700,
            "business_connection_id": "business-connection",
            "chat": {"id": 12345, "type": "private"},
        },
    }

    asyncio.run(telegram_router._handle_payment_callback(Session(), callback))

    assert payment.destination_id == destination.id
    assert payment.destination_snapshot["account_number"] == destination.account_number
    assert [method for method, _ in calls] == ["answerCallbackQuery", "editMessageText"]
    assert calls[1][1]["message_id"] == 700
    assert destination.account_number in calls[1][1]["text"]
    assert calls[1][1]["reply_markup"]["inline_keyboard"][0][0]["copy_text"]["text"] == destination.account_number


def test_expired_callback_uses_locale_encoded_in_the_old_button(monkeypatch):
    calls = []

    class Session:
        async def scalar(self, _query):
            return None

    async def fake_bot_request(_token, method, payload):
        calls.append((method, payload))
        return {}

    monkeypatch.setattr(telegram_router, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(telegram_router, "bot_request", fake_bot_request)
    asyncio.run(
        telegram_router._handle_payment_callback(
            Session(),
            {
                "id": "callback-id",
                "data": "bank:abcdefghijklmnop:a1b2c3d4:uz",
                "from": {"id": 12345},
                "message": {
                    "message_id": 700,
                    "business_connection_id": "business-connection",
                    "chat": {"id": 12345, "type": "private"},
                },
            },
        )
    )

    assert calls[0][0] == "answerCallbackQuery"
    assert "Bank tanlovi yaroqsiz" in calls[0][1]["text"]


def test_callback_from_another_chat_is_rejected_without_selecting_bank(monkeypatch):
    payment = SimpleNamespace(telegram_selection_token="abcdefghijklmnop")
    calls = []

    class Session:
        async def scalar(self, _query):
            return payment

    async def fake_bot_request(_token, method, payload):
        calls.append((method, payload))
        return {}

    monkeypatch.setattr(telegram_router, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(telegram_router, "bot_request", fake_bot_request)
    asyncio.run(
        telegram_router._handle_payment_callback(
            Session(),
            {
                "id": "callback-id",
                "data": "bank:abcdefghijklmnop:a1b2c3d4:en",
                "from": {"id": 67890},
                "message": {
                    "message_id": 700,
                    "business_connection_id": "business-connection",
                    "chat": {"id": 12345, "type": "private"},
                },
            },
        )
    )

    assert calls[0][0] == "answerCallbackQuery"
    assert "no longer valid" in calls[0][1]["text"]


def test_paid_order_rejects_callback_and_removes_buttons(monkeypatch):
    payment = SimpleNamespace(
        telegram_selection_token="abcdefghijklmnop",
        telegram_payment_message_id=700,
        order_id="order-id",
        status="paid",
        destination_snapshot=None,
    )
    order = SimpleNamespace(id="order-id", status="paid")
    inquiry = SimpleNamespace(
        order_id="order-id",
        telegram_connection_id="business-connection",
        telegram_chat_id=12345,
        locale="id",
    )
    calls = []

    class Session:
        values = [payment, order, inquiry]

        async def scalar(self, _query):
            return self.values.pop(0)

    async def fake_bot_request(_token, method, payload):
        calls.append((method, payload))
        return {}

    monkeypatch.setattr(telegram_router, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(telegram_router, "bot_request", fake_bot_request)
    asyncio.run(
        telegram_router._handle_payment_callback(
            Session(),
            {
                "id": "callback-id",
                "data": "bank:abcdefghijklmnop:a1b2c3d4:id",
                "from": {"id": 12345},
                "message": {
                    "message_id": 700,
                    "business_connection_id": "business-connection",
                    "chat": {"id": 12345, "type": "private"},
                },
            },
        )
    )

    assert [method for method, _ in calls] == ["answerCallbackQuery", "editMessageText"]
    assert "sudah diproses" in calls[0][1]["text"]
    assert calls[1][1]["reply_markup"] == {"inline_keyboard": []}


def test_webhook_readiness_requires_callback_query(monkeypatch):
    async def ready_without_callbacks(*_args, **_kwargs):
        return {
            "url": "https://shop.example.test/api/v1/telegram/webhook",
            "allowed_updates": ["business_connection", "business_message"],
            "pending_update_count": 0,
        }

    monkeypatch.setattr("telegram_inquiries.bot_request", ready_without_callbacks)
    assert not asyncio.run(
        telegram_webhook_is_ready(
            "token", "https://shop.example.test/api/v1/telegram/webhook"
        )
    )
