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


SUPPORTED_TELEGRAM_LOCALES = {"id", "en", "uz", "ru"}


def normalized_telegram_locale(value: object, default: str = "uz") -> str:
    code = str(value or "").lower().replace("_", "-").split("-", 1)[0]
    return code if code in SUPPORTED_TELEGRAM_LOCALES else default


def apply_web_locale(conversation: TelegramConversation, locale: str) -> None:
    conversation.locale = normalized_telegram_locale(locale)
    conversation.locale_source = "web"
    conversation.updated_at = utcnow()


def apply_direct_default_locale(conversation: TelegramConversation) -> str:
    if conversation.locale_source != "admin":
        conversation.locale = "uz"
        conversation.locale_source = "direct_default"
        conversation.updated_at = utcnow()
    return normalized_telegram_locale(conversation.locale)


async def active_locale_for_chat(
    session: AsyncSession,
    connection_id: str,
    chat_id: int,
    fallback: str = "uz",
) -> str:
    conversation = await session.scalar(
        select(TelegramConversation).where(
            TelegramConversation.connection_id == connection_id,
            TelegramConversation.chat_id == chat_id,
        )
    )
    return normalized_telegram_locale(
        conversation.locale if conversation else fallback, default=fallback
    )


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


def _rich_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_rich_text(item) for item in value)
    if not isinstance(value, dict):
        return ""
    if value.get("type") == "custom_emoji":
        return str(value.get("alternative_text") or "")
    if isinstance(value.get("text"), (str, list, dict)):
        return _rich_text(value["text"])
    if isinstance(value.get("expression"), str):
        return value["expression"]
    return ""


def _largest_photo(photo_sizes: object) -> dict | None:
    photos = photo_sizes if isinstance(photo_sizes, list) else []

    def size(photo: dict) -> int:
        try:
            return int(photo.get("file_size") or 0)
        except (TypeError, ValueError):
            return 0

    return max(
        (photo for photo in photos if isinstance(photo, dict)),
        key=size,
        default=None,
    )


def normalize_rich_content(message: dict) -> dict | None:
    """Keep only the cart slideshow fields CMS needs; never persist arbitrary HTML."""
    rich_message = message.get("rich_message")
    blocks = rich_message.get("blocks") if isinstance(rich_message, dict) else None
    if not isinstance(blocks, list):
        return None

    title = ""
    intro = ""
    slides: list[dict] = []
    footer: list[str] = []
    after_slideshow = False
    for block in blocks:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "heading":
            title = _rich_text(block.get("text"))
        elif kind in {"paragraph", "footer"}:
            text = _rich_text(block.get("text"))
            if not text:
                continue
            if not after_slideshow and not intro:
                intro = text
            else:
                footer.append(text)
        elif kind == "divider":
            continue
        elif kind == "slideshow":
            after_slideshow = True
            slide_blocks = block.get("blocks")
            for slide_block in slide_blocks if isinstance(slide_blocks, list) else []:
                if not isinstance(slide_block, dict):
                    continue
                photo = _largest_photo(slide_block.get("photo")) if slide_block.get("type") == "photo" else None
                caption = _rich_text(slide_block.get("caption"))
                if not caption:
                    caption = _rich_text(slide_block.get("text"))
                if not photo and not caption:
                    continue
                slides.append(
                    {
                        "caption": caption,
                        "photo_file_id": str(photo.get("file_id") or "")[:512] or None if photo else None,
                        "photo_file_unique_id": str(photo.get("file_unique_id") or "")[:128] or None if photo else None,
                        "photo_file_size": int(photo.get("file_size") or 0) or None if photo else None,
                    }
                )
    if not any((title, intro, slides, footer)):
        return None
    return {"title": title, "intro": intro, "slides": slides, "footer": footer}


async def get_or_create_conversation(
    session: AsyncSession,
    connection: TelegramBusinessConnection,
    chat: dict,
    sender: dict,
    at: datetime,
    *,
    sender_is_customer: bool | None = None,
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
    is_customer = sender_is_customer
    if is_customer is None:
        is_customer = (
            str(sender.get("id") or "") != connection.business_user_id
            and not sender.get("is_bot")
        )
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
            use_telegram_locale = (
                not row.telegram_language_code
                and getattr(row, "locale_source", "legacy") == "legacy"
            )
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
    session: AsyncSession,
    message: dict,
    update_id: int | None,
    *,
    edited: bool = False,
    allow_outgoing_without_read: bool = False,
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
    if not connection:
        return None

    sender_is_customer = not (
        isinstance(message.get("sender_business_bot"), dict)
        or str(sender.get("id") or "") == connection.business_user_id
        or sender.get("is_bot")
    )
    if (
        not connection.is_enabled
        or connection.username.casefold().lstrip("@")
        != TELEGRAM_STORE_USERNAME.casefold().lstrip("@")
        or (
            not connection.can_read_messages
            and (sender_is_customer or not allow_outgoing_without_read)
        )
    ):
        return None

    photo = _largest_photo(message.get("photo"))
    rich_content = normalize_rich_content(message)
    text = message.get("text") or message.get("caption") or ""
    if not isinstance(text, str):
        text = ""
    if not photo and not text.strip() and not rich_content:
        return None

    at = message_datetime(message, edited=edited)
    conversation = await get_or_create_conversation(
        session,
        connection,
        chat,
        sender,
        at,
        sender_is_customer=sender_is_customer,
    )
    row = await session.scalar(
        select(TelegramInboxMessage).where(
            TelegramInboxMessage.connection_id == connection_id,
            TelegramInboxMessage.chat_id == chat["id"],
            TelegramInboxMessage.telegram_message_id == message_id,
        )
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
    row.message_type = "rich" if rich_content else "photo" if photo else "text"
    row.text = text[:4096]
    row.rich_content = rich_content
    row.media_group_id = str(message.get("media_group_id") or "")[:255] or None
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
    allow_outgoing_without_read: bool = False,
) -> None:
    """Persist a chat update; duplicate message IDs update the same row."""
    try:
        row = await persist_business_message(
            session,
            message,
            update_id,
            edited=edited,
            allow_outgoing_without_read=allow_outgoing_without_read,
        )
        if row and source_override:
            row.source = source_override
        await session.commit()
    except IntegrityError:
        await session.rollback()
        # A Telegram edit/send echo can race a webhook delivery. The message
        # unique key makes the operation safe; retry the upsert once.
        row = await persist_business_message(
            session,
            message,
            update_id,
            edited=edited,
            allow_outgoing_without_read=allow_outgoing_without_read,
        )
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
    message_type: str | None = None,
    source_override: str | None = "cms",
) -> None:
    """Mirror server-sent Business messages into the same CMS transcript."""
    if isinstance(result, list):
        for sent_message in result:
            if isinstance(sent_message, dict):
                await record_outgoing_message(
                    session,
                    connection_id,
                    chat_id,
                    sent_message,
                    text,
                    message_type=message_type,
                    source_override=source_override,
                )
        return
    connection = await session.get(TelegramBusinessConnection, connection_id)
    message_id = result.get("message_id") if isinstance(result, dict) else None
    if not connection or not isinstance(message_id, int):
        return
    payload = dict(result)
    payload["business_connection_id"] = connection_id
    payload["message_id"] = message_id
    payload["date"] = payload.get("date") if isinstance(payload.get("date"), int) else int(time.time())
    payload["chat"] = (
        payload.get("chat")
        if isinstance(payload.get("chat"), dict)
        else {"type": "private", "id": chat_id}
    )
    payload["chat"].setdefault("type", "private")
    payload["chat"].setdefault("id", chat_id)
    payload["from"] = (
        payload.get("from")
        if isinstance(payload.get("from"), dict)
        else {"id": connection.business_user_id, "is_bot": True}
    )
    if text and not payload.get("text") and not payload.get("caption"):
        if message_type == "photo":
            payload["caption"] = text
        elif message_type != "rich":
            payload["text"] = text
    await capture_business_message(
        session,
        payload,
        None,
        source_override=source_override,
        allow_outgoing_without_read=True,
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
            rich_content=None,
            media_group_id=None,
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
    question, sku_label, quantity_label = labels.get(
        normalized_telegram_locale(locale), labels["uz"]
    )
    return f"{product_name}\n{sku_label}: {sku}\n{quantity_label}: {quantity}\n\n{question}"


def candidate_keyboard(token: str, locale: str) -> dict:
    labels = {
        "id": ("Ya, benar", "Bukan, cari lagi"),
        "en": ("Yes, correct", "No, find another"),
        "uz": ("Ha, to‘g‘ri", "Yo‘q, boshqasini qidiring"),
        "ru": ("Да, верно", "Нет, найти другой"),
    }
    yes, no = labels.get(normalized_telegram_locale(locale), labels["uz"])
    return {
        "inline_keyboard": [[
            {"text": yes, "callback_data": f"CAT:{token}:yes"},
            {"text": no, "callback_data": f"CAT:{token}:no"},
        ]]
    }


def candidate_callback_error(locale: str, key: str) -> str:
    copy = {
        "id": {
            "invalid": "Pilihan ini tidak valid atau sudah kedaluwarsa.",
            "inactive": "Pilihan ini sudah tidak aktif. Admin akan membantu Anda.",
        },
        "en": {
            "invalid": "This choice is invalid or has expired.",
            "inactive": "This choice is no longer active. An admin will help you.",
        },
        "uz": {
            "invalid": "Bu tanlov noto‘g‘ri yoki muddati tugagan.",
            "inactive": "Bu tanlov endi faol emas. Admin sizga yordam beradi.",
        },
        "ru": {
            "invalid": "Этот вариант недействителен или срок его действия истёк.",
            "inactive": "Этот вариант больше не активен. Вам поможет администратор.",
        },
    }
    locale = normalized_telegram_locale(locale)
    return copy[locale][key]
