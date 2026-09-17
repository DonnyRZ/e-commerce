import asyncio
import json

import pytest
from fastapi import HTTPException, Request

import routers.telegram as telegram_router
import telegram_inquiries
from telegram_inquiries import (
    TelegramDeliveryError,
    make_snapshot,
    prefilled_message,
    rich_message,
    send_inquiry,
    summary_chunks,
    summary_text,
)


def _cart():
    return {
        "subtotal": 378000,
        "currency": "UZS",
        "item_count": 3,
        "items": [
            {
                "translations": {"id": {"title": "Musk <Tharah>"}},
                "slug": "musk-tharah",
                "option_values": {"Size": "30 ml"},
                "sku": "DEMO-30ML",
                "quantity": 2,
                "unit_price": 189000,
                "line_total": 378000,
                "availability": "in_stock",
                "image_url": "https://cdn.example.test/musk.jpg",
            },
            {
                "translations": {"en": {"title": "No photo item"}},
                "slug": "no-photo",
                "option_values": {},
                "sku": "NO-PHOTO",
                "quantity": 1,
                "unit_price": 0,
                "line_total": 0,
                "availability": "out_of_stock",
                "image_url": None,
            },
        ],
    }


def test_snapshot_uses_server_cart_values_and_all_items(monkeypatch):
    monkeypatch.setattr(telegram_inquiries, "FRONTEND_URL", "https://shanicantik.com")
    snapshot = make_snapshot(_cart(), "id")

    assert snapshot["subtotal"] == 378000
    assert snapshot["item_count"] == 3
    assert [item["name"] for item in snapshot["items"]] == [
        "Musk <Tharah>",
        "No photo item",
    ]
    assert snapshot["items"][0]["image_url"] == "https://cdn.example.test/musk.jpg"
    assert snapshot["items"][1]["image_url"] is None
    assert "No photo item" in summary_text(snapshot, "SC-" + "A" * 32)


def test_long_fallback_summary_keeps_every_item_under_telegram_text_limit():
    cart = _cart()
    cart["items"] = [
        {
            "translations": {"en": {"title": f"Product {index}"}},
            "quantity": 1,
            "line_total": 1000,
            "unit_price": 1000,
            "sku": f"SKU-{index}",
            "option_values": {},
            "availability": "in_stock",
            "image_url": None,
        }
        for index in range(90)
    ]
    snapshot = make_snapshot(cart, "en")
    chunks = summary_chunks(snapshot, "SC-" + "A" * 32)

    assert len(chunks) > 1
    assert all(len(chunk) <= 3800 for chunk in chunks)
    assert all(f"Product {index}" in "\n".join(chunks) for index in range(90))


def test_rich_message_has_a_slide_for_each_item_and_escapes_content(monkeypatch):
    monkeypatch.setattr(telegram_inquiries, "FRONTEND_URL", "https://shanicantik.com")
    result = rich_message(make_snapshot(_cart(), "id"), "SC-" + "A" * 32)
    rich_html = result["html"]

    assert rich_html.count("<figure>") == 2
    assert "<img src=\"https://cdn.example.test/musk.jpg\"/>" in rich_html
    assert "Musk &lt;Tharah&gt;" in rich_html
    assert "out of stock" not in rich_html
    assert "bukan pesanan final" in rich_html.lower()


@pytest.mark.parametrize("locale", ["id", "en", "uz", "ru"])
def test_deep_link_prompt_has_a_localized_reference(locale):
    message = prefilled_message(locale, "SC-" + "F" * 32)
    assert "SC-" + "F" * 32 in message
    assert message


def test_successful_rich_send_uses_business_identity_and_no_paid_parameters(monkeypatch):
    calls = []

    async def fake_bot_request(token, method, payload):
        calls.append((token, method, payload))
        return {"message_id": 1}

    monkeypatch.setattr(telegram_inquiries, "bot_request", fake_bot_request)
    snapshot = make_snapshot(_cart(), "en")
    result = asyncio.run(
        send_inquiry("test-token", "business-connection", 12345, snapshot, "SC-" + "B" * 32)
    )

    assert result == "rich"
    assert len(calls) == 1
    assert calls[0][1] == "sendRichMessage"
    assert calls[0][2]["business_connection_id"] == "business-connection"
    assert calls[0][2]["chat_id"] == 12345
    assert "allow_paid_broadcast" not in calls[0][2]


def test_rich_rejection_falls_back_to_standard_album_and_summary(monkeypatch):
    calls = []

    async def fake_bot_request(token, method, payload):
        calls.append((method, payload))
        if method == "sendRichMessage":
            raise TelegramDeliveryError("rejected")
        return {}

    monkeypatch.setattr(telegram_inquiries, "bot_request", fake_bot_request)
    cart = _cart()
    cart["items"][1]["image_url"] = "https://cdn.example.test/second.jpg"
    snapshot = make_snapshot(cart, "en")
    result = asyncio.run(
        send_inquiry("test-token", "business-connection", 12345, snapshot, "SC-" + "C" * 32)
    )

    assert result == "album"
    assert [method for method, _ in calls] == ["sendRichMessage", "sendMediaGroup", "sendMessage"]
    assert "No photo item" in calls[-1][1]["text"]
    assert all("allow_paid_broadcast" not in payload for _, payload in calls)


def _request(payload, secret="test-secret"):
    body = json.dumps(payload).encode()
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/telegram/webhook",
        "headers": [(b"x-telegram-bot-api-secret-token", secret.encode())],
        "query_string": b"",
        "server": ("testserver", 443),
        "client": ("127.0.0.1", 1234),
        "scheme": "https",
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


def test_webhook_rejects_wrong_secret_before_parsing(monkeypatch):
    monkeypatch.setattr(telegram_router, "TELEGRAM_BOT_TOKEN", "configured")
    monkeypatch.setattr(telegram_router, "TELEGRAM_WEBHOOK_SECRET", "test-secret")
    request = _request({"update_id": 1}, secret="wrong-secret")

    with pytest.raises(HTTPException) as error:
        asyncio.run(telegram_router.telegram_webhook(request, "wrong-secret", object()))
    assert error.value.status_code == 403


def test_store_username_matching_ignores_at_prefix_and_case():
    assert telegram_router._normalized_username("@CantikByIndonesia") == "cantikbyindonesia"
    assert telegram_router._normalized_username("cantikbyindonesia") == "cantikbyindonesia"


def test_duplicate_webhook_update_is_acknowledged_without_processing(monkeypatch):
    monkeypatch.setattr(telegram_router, "TELEGRAM_BOT_TOKEN", "configured")
    monkeypatch.setattr(telegram_router, "TELEGRAM_WEBHOOK_SECRET", "test-secret")

    async def no_expiry(_session):
        return None

    async def already_claimed(_session, _update_id):
        return False

    async def must_not_process(*_args):
        raise AssertionError("duplicate webhook update was processed twice")

    monkeypatch.setattr(telegram_router, "_expire_old_snapshots", no_expiry)
    monkeypatch.setattr(telegram_router, "_claim_update", already_claimed)
    monkeypatch.setattr(telegram_router, "_handle_business_message", must_not_process)
    request = _request({"update_id": 55, "business_message": {"text": "SC-" + "D" * 32}})

    result = asyncio.run(
        telegram_router.telegram_webhook(request, "test-secret", object())
    )
    assert result == {"ok": True, "duplicate": True}


def test_disabled_feature_does_not_send_existing_inquiries(monkeypatch):
    monkeypatch.setattr(telegram_router, "TELEGRAM_BOT_TOKEN", "configured")
    monkeypatch.setattr(telegram_router, "TELEGRAM_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setattr(telegram_router, "TELEGRAM_INQUIRIES_ENABLED", False)
    calls = []

    async def no_expiry(_session):
        return None

    async def claim(_session, _update_id):
        return True

    async def store_connection(_session, _payload):
        calls.append("connection")

    async def must_not_send(*_args):
        raise AssertionError("disabled feature sent a Telegram reply")

    class Receipt:
        status = "processing"

    class Session:
        receipt = Receipt()

        async def get(self, _model, _update_id):
            return self.receipt

        async def commit(self):
            return None

    monkeypatch.setattr(telegram_router, "_expire_old_snapshots", no_expiry)
    monkeypatch.setattr(telegram_router, "_claim_update", claim)
    monkeypatch.setattr(telegram_router, "_store_connection", store_connection)
    monkeypatch.setattr(telegram_router, "_handle_business_message", must_not_send)
    request = _request(
        {
            "update_id": 56,
            "business_connection": {"id": "connection"},
            "business_message": {"text": "SC-" + "E" * 32},
        }
    )

    result = asyncio.run(
        telegram_router.telegram_webhook(request, "test-secret", Session())
    )
    assert result == {"ok": True}
    assert calls == ["connection"]
