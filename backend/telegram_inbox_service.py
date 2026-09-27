"""Persistence and Telegram delivery helpers for the Business inbox."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_STORE_USERNAME
from db.models import (
    TelegramBusinessConnection,
    TelegramConversation,
    TelegramInboxMessage,
    TelegramProductCandidate,
    utcnow,
)
from telegram_inquiries import TelegramDeliveryError, bot_request


def message_datetime(message: dict, *, edited: bool = False) -> datetime:
    timestamp = message.get("edit_date") if edited else message.get("date")
    if not isinstance(timestamp, int) or isinstance(timestamp, bool):
        timestamp = message.get("date")
    if isinstance(timestamp, int) and not isinstance(timestamp, bool):
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return utcnow()


def locale_from_language(value: object) -> str:
    code = str(value or "").lower().replace("_", "-").split("-", 1)[0]
    return code if code in {"id", "en", "uz", "ru"} else "id"


async def get_or_create_conversation(
    session: AsyncSession,
    connection: TelegramBusinessConnection,
    chat: dict,
    sender: dict,
    at: datetime,
) -> TelegramConversation:
    chat_id = chat.get("id")
    row = await session.scalar(
        select(TelegramConversation)
        .where(
            TelegramConversation.connection_id == connection.connection_id,
            TelegramConversation.chat_id == chat_id,
        )
        .with_for_update()
    )
    is_customer = str(sender.get("id") or "") != connection.business_user_id and not sender.get("is_bot")
    if row is None:
        customer = sender if is_customer else chat
        language = str(customer.get("language_code") or "")[:16]
        row = TelegramConversation(
            connection_id=connection.connection_id,
            chat_id=chat_id,
            customer_user_id=str(chat_id or "")[:32] or None,
            customer_username=str(customer.get("username") or "")[:64],
            customer_name=(
                " ".join(
                    str(customer.get(key) or "").strip()
                    for key in ("first_name", "last_name")
                    if str(customer.get(key) or "").strip()
                )
                or str(chat.get("title") or "Telegram customer")
            )[:160],
            telegram_language_code=language,
            locale=locale_from_language(language),
            status="needs_admin" if is_customer else "waiting_customer",
            last_message_at=at,
            last_customer_message_at=at if is_customer else None,
            last_admin_message_at=None if is_customer else at,
        )
        session.add(row)
        await session.flush()
        return row

    if is_customer:
        row.customer_user_id = str(sender.get("id") or row.customer_user_id or "")[:32] or None
        row.customer_username = str(sender.get("username") or row.customer_username or "")[:64]
        name = " ".join(
            str(sender.get(key) or "").strip()
            for key in ("first_name", "last_name")
            if str(sender.get(key) or "").strip()
        )
        if name:
            row.customer_name = name[:160]
        language = str(sender.get("language_code") or "")[:16]
        if language:
            use_telegram_locale = not row.telegram_language_code
            row.telegram_language_code = language
            if use_telegram_locale:
                row.locale = locale_from_language(language)
        if row.last_customer_message_at is None or at > row.last_customer_message_at:
            row.last_customer_message_at = at
        row.status = "needs_admin"
    else:
        if row.last_admin_message_at is None or at > row.last_admin_message_at:
            row.last_admin_message_at = at
        if row.status not in {"archived", "ready_for_order"}:
            row.status = "waiting_customer"
    if at > row.last_message_at:
        row.last_message_at = at
    row.updated_at = utcnow()
    return row


async def persist_business_message(
    session: AsyncSession, message: dict, update_id: int | None, *, edited: bool = False
) -> TelegramInboxMessage | None:
    connection_id = message.get("business_connection_id")
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    sender = message.get("from") if isinstance(message.get("from"), dict) else {}
    message_id = message.get("message_id")
    if (
        not isinstance(connection_id, str)
        or chat.get("type") != "private"
        or not isinstance(chat.get("id"), int)
        or isinstance(chat.get("id"), bool)
        or not isinstance(message_id, int)
        or isinstance(message_id, bool)
    ):
        return None
    connection = await session.get(TelegramBusinessConnection, connection_id)
    if connection is None and TELEGRAM_BOT_TOKEN:
        details = await bot_request(
            TELEGRAM_BOT_TOKEN,
            "getBusinessConnection",
            {"business_connection_id": connection_id},
        )
        if details.get("id") == connection_id:
            business_user = details.get("user") if isinstance(details.get("user"), dict) else {}
            rights = details.get("rights") if isinstance(details.get("rights"), dict) else {}
            connection = TelegramBusinessConnection(
                connection_id=connection_id,
                business_user_id=str(business_user.get("id") or "")[:32],
                username=str(business_user.get("username") or "").casefold().lstrip("@")[:32],
                is_enabled=bool(details.get("is_enabled")),
                can_reply=bool(rights.get("can_reply")),
                can_read_messages=bool(rights.get("can_read_messages")),
            )
            session.add(connection)
            await session.flush()
    if (
        not connection
        or not connection.is_enabled
        or connection.username.casefold().lstrip("@")
        != TELEGRAM_STORE_USERNAME.casefold().lstrip("@")
        or not connection.can_read_messages
    ):
        return None

    photo_sizes = message.get("photo") if isinstance(message.get("photo"), list) else []
    photo = max(
        (item for item in photo_sizes if isinstance(item, dict)),
        key=lambda item: int(item.get("file_size") or 0),
        default=None,
    )
    text = message.get("text") or message.get("caption") or ""
    if not isinstance(text, str):
        text = ""
    if not photo and not text.strip():
        return None

    at = message_datetime(message, edited=edited)
    conversation = await get_or_create_conversation(session, connection, chat, sender, at)
    row = await session.scalar(
        select(TelegramInboxMessage).where(
            TelegramInboxMessage.connection_id == connection_id,
            TelegramInboxMessage.chat_id == chat["id"],
            TelegramInboxMessage.telegram_message_id == message_id,
        )
    )
    sender_is_customer = (
        str(sender.get("id") or "") != connection.business_user_id
        and not sender.get("is_bot")
    )
    if row is None:
        row = TelegramInboxMessage(
            conversation_id=conversation.id,
            connection_id=connection_id,
            chat_id=chat["id"],
            telegram_message_id=message_id,
            update_id=update_id,
            sender_user_id=str(sender.get("id") or "")[:32] or None,
            direction="inbound" if sender_is_customer else "outbound",
            source="telegram",
            created_at=at,
        )
        session.add(row)
    if update_id is not None:
        row.update_id = update_id
    row.message_type = "photo" if photo else "text"
    row.text = text[:4096]
    row.photo_file_id = str(photo.get("file_id") or "")[:512] or None if photo else None
    row.photo_file_unique_id = str(photo.get("file_unique_id") or "")[:128] or None if photo else None
    row.photo_file_size = int(photo.get("file_size") or 0) or None if photo else None
    row.deleted_at = None
    row.edited_at = utcnow() if edited else row.edited_at
    await session.flush()
    return row


async def capture_business_message(
    session: AsyncSession,
    message: dict,
    update_id: int | None,
    *,
    edited: bool = False,
    source_override: str | None = None,
) -> None:
    """Persist a chat update; duplicate message IDs update the same row."""
    try:
        row = await persist_business_message(session, message, update_id, edited=edited)
        if row and source_override:
            row.source = source_override
        await session.commit()
    except IntegrityError:
        await session.rollback()
        # A Telegram edit/send echo can race a webhook delivery. The message
        # unique key makes the operation safe; retry the upsert once.
        row = await persist_business_message(session, message, update_id, edited=edited)
        if row and source_override:
            row.source = source_override
        await session.commit()


async def record_outgoing_message(
    session: AsyncSession,
    connection_id: str,
    chat_id: int,
    result: dict,
    text: str,
    *,
    message_type: str = "text",
) -> None:
    """Mirror server-sent Business messages into the same CMS transcript."""
    connection = await session.get(TelegramBusinessConnection, connection_id)
    message_id = result.get("message_id") if isinstance(result, dict) else None
    if not connection or not isinstance(message_id, int):
        return
    payload = {
        "business_connection_id": connection_id,
        "message_id": message_id,
        "date": int(time.time()),
        "chat": {"type": "private", "id": chat_id},
        "from": {"id": connection.business_user_id, "is_bot": True},
        "text": text if message_type == "text" else "",
        "caption": text if message_type == "photo" else "",
        "photo": result.get("photo", []) if isinstance(result.get("photo"), list) else [],
    }
    await capture_business_message(
        session, payload, None, source_override="cms"
    )


async def capture_deleted_messages(session: AsyncSession, update: dict) -> None:
    connection_id = update.get("business_connection_id")
    chat = update.get("chat") if isinstance(update.get("chat"), dict) else {}
    ids = update.get("message_ids")
    if not isinstance(connection_id, str) or not isinstance(chat.get("id"), int) or not isinstance(ids, list):
        return
    valid_ids = [value for value in ids if isinstance(value, int) and not isinstance(value, bool)]
    if not valid_ids:
        return
    from sqlalchemy import update as sql_update

    await session.execute(
        sql_update(TelegramInboxMessage)
        .where(
            TelegramInboxMessage.connection_id == connection_id,
            TelegramInboxMessage.chat_id == chat["id"],
            TelegramInboxMessage.telegram_message_id.in_(valid_ids),
        )
        .values(
            text="",
            photo_file_id=None,
            photo_file_unique_id=None,
            photo_file_size=None,
            deleted_at=utcnow(),
        )
    )
    await session.commit()


def candidate_copy(locale: str, product_name: str, sku: str, quantity: int) -> str:
    labels = {
        "id": ("Apakah ini produk yang Anda maksud?", "SKU", "Jumlah"),
        "en": ("Is this the product you mean?", "SKU", "Quantity"),
        "uz": ("Siz nazarda tutgan mahsulot shu-mi?", "SKU", "Miqdor"),
        "ru": ("Это тот товар, который вы имели в виду?", "Артикул", "Количество"),
    }
    question, sku_label, quantity_label = labels.get(locale, labels["id"])
    return f"{product_name}\n{sku_label}: {sku}\n{quantity_label}: {quantity}\n\n{question}"


def candidate_keyboard(token: str, locale: str) -> dict:
    labels = {
        "id": ("Ya, benar", "Bukan, cari lagi"),
        "en": ("Yes, correct", "No, find another"),
        "uz": ("Ha, to‘g‘ri", "Yo‘q, boshqasini qidiring"),
        "ru": ("Да, верно", "Нет, найти другой"),
    }
    yes, no = labels.get(locale, labels["id"])
    return {
        "inline_keyboard": [[
            {"text": yes, "callback_data": f"CAT:{token}:yes"},
            {"text": no, "callback_data": f"CAT:{token}:no"},
        ]]
    }
