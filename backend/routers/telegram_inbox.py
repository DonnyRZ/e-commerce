"""Admin API for Telegram Business chat and chat-originated orders."""

from __future__ import annotations

import secrets
import uuid
from datetime import timedelta
from typing import Any, Literal, Optional
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth import csrf_protect, require_roles
from cms.service import audit
from config import APP_ENV, FRONTEND_URL, TELEGRAM_BOT_TOKEN
from db.models import (
    Category,
    Order,
    OrderItem,
    Payment,
    Product,
    ProductTranslation,
    ProductVariant,
    TelegramBusinessConnection,
    TelegramConversation,
    TelegramInboxMessage,
    TelegramProductCandidate,
    User,
    utcnow,
)
from db.session import get_session
from telegram_inbox_service import candidate_copy, candidate_keyboard
from telegram_inquiries import TelegramDeliveryError, bot_request, bot_request_multipart
from product_sizes import load_size_preset_data, size_variant_is_visible

router = APIRouter(prefix="/api/v1/admin/telegram-inbox", tags=["telegram-inbox"])
require_admin = require_roles("admin")
MAX_CHAT_PHOTO_BYTES = 8 * 1024 * 1024
ALLOWED_CHAT_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}


class MessageTextIn(BaseModel):
    text: str = Field(min_length=1, max_length=4096)


class CandidateCreateIn(BaseModel):
    product_id: str = Field(min_length=1, max_length=32)
    variant_id: str = Field(min_length=1, max_length=32)
    quantity: int = Field(default=1, ge=1, le=99)
    source_message_id: Optional[str] = Field(default=None, max_length=32)


class CandidateReviewIn(BaseModel):
    status: Literal["confirmed", "rejected"]


class ConversationUpdateIn(BaseModel):
    locale: Optional[Literal["id", "en", "uz", "ru"]] = None
    status: Optional[Literal["needs_admin", "waiting_customer", "ready_for_order", "archived"]] = None


class InboxOrderCreateIn(BaseModel):
    candidate_ids: list[str] = Field(min_length=1, max_length=50)
    guest_email: Optional[str] = Field(default=None, max_length=255)
    shipping_address: dict[str, Any] = Field(default_factory=dict)
    shipping_method: str = Field(default="manual", min_length=1, max_length=80)
    shipping_amount: int = Field(default=0, ge=0)


def _error(status: int, code: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": code, **extra})


def _price(product: Product, variant: ProductVariant) -> int:
    if variant.sale_price_override is not None:
        return int(variant.sale_price_override)
    if variant.price_override is not None:
        return int(variant.price_override)
    return int(product.base_price)


def _media_url(product: Product, variant: ProductVariant) -> Optional[str]:
    candidate = variant.image_url
    if not candidate:
        media = product.media if isinstance(product.media, list) else []
        candidate = next(
            (item.get("url") for item in media if isinstance(item, dict) and isinstance(item.get("url"), str)),
            None,
        )
    if isinstance(candidate, str) and candidate.strip():
        absolute = urljoin(f"{FRONTEND_URL.rstrip('/')}/", candidate.strip())
        if urlparse(absolute).scheme in {"http", "https"}:
            return absolute
    return None


def _option_label(values: dict) -> str:
    return " / ".join(f"{key}: {value}" for key, value in values.items() if value not in (None, ""))


async def _load_conversation(session: AsyncSession, conversation_id: str) -> TelegramConversation:
    row = await session.scalar(
        select(TelegramConversation)
        .where(TelegramConversation.id == conversation_id)
        .with_for_update()
    )
    if not row:
        raise _error(404, "conversation_not_found")
    return row


async def _reply_context(session: AsyncSession, conversation: TelegramConversation):
    connection = await session.get(TelegramBusinessConnection, conversation.connection_id)
    if (
        not connection
        or not connection.is_enabled
        or not connection.can_reply
        or not connection.can_read_messages
    ):
        raise _error(409, "telegram_business_reply_unavailable")
    last_inbound = conversation.last_customer_message_at
    if not last_inbound or utcnow() - last_inbound > timedelta(hours=24):
        raise _error(409, "telegram_reply_window_expired")
    if conversation.status == "archived":
        raise _error(409, "conversation_archived")
    if not TELEGRAM_BOT_TOKEN:
        raise _error(503, "telegram_not_configured")
    return connection


def _message_payload(row: TelegramInboxMessage) -> dict:
    return {
        "id": row.id,
        "telegram_message_id": row.telegram_message_id,
        "direction": row.direction,
        "source": row.source,
        "type": row.message_type,
        "text": row.text,
        "photo_url": (
            f"/api/v1/admin/telegram-inbox/media/{row.id}"
            if row.photo_file_id and not row.deleted_at
            else None
        ),
        "is_deleted": row.deleted_at is not None,
        "created_at": row.created_at,
        "edited_at": row.edited_at,
    }


def _conversation_payload(row: TelegramConversation, last_message: Optional[TelegramInboxMessage]) -> dict:
    now = utcnow()
    can_send = bool(
        row.status != "archived"
        and row.last_customer_message_at
        and now - row.last_customer_message_at <= timedelta(hours=24)
    )
    return {
        "id": row.id,
        "chat_id": row.chat_id,
        "customer_user_id": row.customer_user_id,
        "customer_username": row.customer_username,
        "customer_name": row.customer_name or "Telegram customer",
        "telegram_language_code": row.telegram_language_code,
        "locale": row.locale,
        "status": row.status,
        "last_message_at": row.last_message_at,
        "last_customer_message_at": row.last_customer_message_at,
        "can_send": can_send,
        "last_message": _message_payload(last_message) if last_message else None,
    }


async def _save_cms_message(
    session: AsyncSession,
    conversation: TelegramConversation,
    result: dict,
    text: str,
    message_type: str,
) -> TelegramInboxMessage:
    message_id = result.get("message_id")
    if not isinstance(message_id, int):
        raise _error(502, "telegram_message_id_missing")
    existing = await session.scalar(
        select(TelegramInboxMessage).where(
            TelegramInboxMessage.connection_id == conversation.connection_id,
            TelegramInboxMessage.chat_id == conversation.chat_id,
            TelegramInboxMessage.telegram_message_id == message_id,
        )
    )
    if existing:
        existing.source = "cms"
        existing.direction = "outbound"
        existing.text = text
        existing.message_type = message_type
        row = existing
    else:
        photos = result.get("photo") if isinstance(result.get("photo"), list) else []
        photo = max(photos, key=lambda item: int(item.get("file_size") or 0), default={})
        row = TelegramInboxMessage(
            conversation_id=conversation.id,
            connection_id=conversation.connection_id,
            chat_id=conversation.chat_id,
            telegram_message_id=message_id,
            sender_user_id=None,
            direction="outbound",
            source="cms",
            message_type=message_type,
            text=text,
            photo_file_id=photo.get("file_id"),
            photo_file_unique_id=photo.get("file_unique_id"),
            photo_file_size=photo.get("file_size"),
        )
        session.add(row)
    now = utcnow()
    conversation.last_message_at = now
    conversation.last_admin_message_at = now
    if conversation.status not in {"archived", "ready_for_order"}:
        conversation.status = "waiting_customer"
    await session.flush()
    return row


@router.get("")
async def list_conversations(
    status: str = Query(default="all", pattern="^(all|needs_admin|waiting_customer|ready_for_order|archived)$"),
    q: Optional[str] = Query(default=None, max_length=120),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    query = select(TelegramConversation)
    if status != "all":
        query = query.where(TelegramConversation.status == status)
    if q and q.strip():
        needle = f"%{q.strip()}%"
        query = query.where(
            or_(
                TelegramConversation.customer_name.ilike(needle),
                TelegramConversation.customer_username.ilike(needle),
                cast(TelegramConversation.chat_id, String).ilike(needle),
            )
        )
    rows = (
        await session.execute(
            query.order_by(TelegramConversation.last_message_at.desc()).limit(100)
        )
    ).scalars().all()
    items = []
    for row in rows:
        last_message = await session.scalar(
            select(TelegramInboxMessage)
            .where(TelegramInboxMessage.conversation_id == row.id)
            .order_by(TelegramInboxMessage.created_at.desc(), TelegramInboxMessage.id.desc())
            .limit(1)
        )
        items.append(_conversation_payload(row, last_message))
    return {"items": items}


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(TelegramConversation, conversation_id)
    if not row:
        raise _error(404, "conversation_not_found")
    messages = (
        await session.execute(
            select(TelegramInboxMessage)
            .where(TelegramInboxMessage.conversation_id == row.id)
            .order_by(TelegramInboxMessage.created_at.desc(), TelegramInboxMessage.id.desc())
            .limit(300)
        )
    ).scalars().all()
    candidates = (
        await session.execute(
            select(TelegramProductCandidate)
            .where(TelegramProductCandidate.conversation_id == row.id)
            .order_by(TelegramProductCandidate.created_at.desc())
        )
    ).scalars().all()
    connection = await session.get(TelegramBusinessConnection, row.connection_id)
    payload = _conversation_payload(row, messages[0] if messages else None)
    payload["can_send"] = bool(
        payload["can_send"] and connection and connection.is_enabled and connection.can_reply
    )
    payload["messages"] = [_message_payload(message) for message in reversed(messages)]
    payload["candidates"] = [
        {
            "id": candidate.id,
            "product_id": candidate.product_id,
            "variant_id": candidate.variant_id,
            "sku": candidate.sku,
            "product_name": candidate.product_name,
            "option_values": candidate.option_values or {},
            "quantity": candidate.quantity,
            "status": candidate.status,
            "confirmation_source": candidate.confirmation_source,
            "confirmed_at": candidate.confirmed_at,
            "created_at": candidate.created_at,
            "order_id": candidate.order_id,
        }
        for candidate in candidates
    ]
    return payload


@router.patch("/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    payload: ConversationUpdateIn,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    row = await _load_conversation(session, conversation_id)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(row, key, value)
    await audit(session, user.id, "admin.telegram_inbox.conversation.update", "telegram_conversation", row.id, data)
    await session.commit()
    return _conversation_payload(row, None)


@router.post("/{conversation_id}/messages", status_code=201)
async def send_text_message(
    conversation_id: str,
    payload: MessageTextIn,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    conversation = await _load_conversation(session, conversation_id)
    connection = await _reply_context(session, conversation)
    try:
        result = await bot_request(
            TELEGRAM_BOT_TOKEN,
            "sendMessage",
            {
                "business_connection_id": connection.connection_id,
                "chat_id": conversation.chat_id,
                "text": payload.text.strip(),
            },
        )
    except (TelegramDeliveryError, TimeoutError) as exc:
        raise _error(502, "telegram_message_send_failed") from exc
    row = await _save_cms_message(session, conversation, result, payload.text.strip(), "text")
    await audit(session, user.id, "admin.telegram_inbox.message.send", "telegram_conversation", row.id, {"type": "text"})
    await session.commit()
    return _message_payload(row)


@router.post("/{conversation_id}/photos", status_code=201)
async def send_photo_message(
    conversation_id: str,
    file: UploadFile = File(...),
    caption: str = Form(default="", max_length=1024),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    conversation = await _load_conversation(session, conversation_id)
    connection = await _reply_context(session, conversation)
    if file.content_type not in ALLOWED_CHAT_PHOTO_TYPES:
        raise _error(422, "unsupported_photo_type")
    data = await file.read(MAX_CHAT_PHOTO_BYTES + 1)
    if not data or len(data) > MAX_CHAT_PHOTO_BYTES:
        raise _error(413, "photo_too_large")
    signatures = {
        "image/jpeg": data[:3] == b"\xff\xd8\xff",
        "image/png": data[:8] == b"\x89PNG\r\n\x1a\n",
        "image/webp": data[:4] == b"RIFF" and data[8:12] == b"WEBP",
    }
    if not signatures.get(file.content_type):
        raise _error(422, "invalid_photo_content")
    try:
        result = await bot_request_multipart(
            TELEGRAM_BOT_TOKEN,
            "sendPhoto",
            {
                "business_connection_id": connection.connection_id,
                "chat_id": str(conversation.chat_id),
                "caption": caption.strip(),
            },
            {"photo": (file.filename or "image", data, file.content_type)},
        )
    except (TelegramDeliveryError, TimeoutError) as exc:
        raise _error(502, "telegram_photo_send_failed") from exc
    row = await _save_cms_message(session, conversation, result, caption.strip(), "photo")
    await audit(session, user.id, "admin.telegram_inbox.message.send", "telegram_conversation", row.id, {"type": "photo"})
    await session.commit()
    return _message_payload(row)


@router.get("/media/{message_id}")
async def get_message_photo(
    message_id: str,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(TelegramInboxMessage, message_id)
    if not row or not row.photo_file_id or row.deleted_at:
        raise _error(404, "telegram_photo_not_found")
    if row.photo_file_size and row.photo_file_size > MAX_CHAT_PHOTO_BYTES:
        raise _error(413, "telegram_photo_too_large")
    if not TELEGRAM_BOT_TOKEN:
        raise _error(503, "telegram_not_configured")
    try:
        file_info = await bot_request(
            TELEGRAM_BOT_TOKEN, "getFile", {"file_id": row.photo_file_id}
        )
        file_path = file_info.get("file_path")
        if not isinstance(file_path, str) or ".." in file_path.split("/"):
            raise _error(502, "telegram_photo_unavailable")
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.get(
                f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
            )
        if response.is_error or len(response.content) > MAX_CHAT_PHOTO_BYTES:
            raise _error(502, "telegram_photo_unavailable")
        mime = response.headers.get("content-type", "image/jpeg").split(";", 1)[0]
        if mime not in ALLOWED_CHAT_PHOTO_TYPES:
            mime = "image/jpeg"
    except (httpx.HTTPError, TelegramDeliveryError, TimeoutError) as exc:
        raise _error(502, "telegram_photo_unavailable") from exc
    return Response(
        content=response.content,
        media_type=mime,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/products/search")
async def search_products(
    q: str = Query(min_length=2, max_length=100),
    locale: str = Query(default="id", pattern="^(id|en|uz|ru)$"),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    needle = f"%{q.strip()}%"
    translated_match = select(ProductTranslation.id).where(
        ProductTranslation.product_id == Product.id,
        ProductTranslation.name.ilike(needle),
    ).exists()
    variant_match = select(ProductVariant.id).where(
        ProductVariant.product_id == Product.id,
        ProductVariant.is_active.is_(True),
        ProductVariant.sku.ilike(needle),
    ).exists()
    products = (
        await session.execute(
            select(Product)
            .where(
                Product.status == "active",
                Product.is_demo.is_(False),
                or_(
                    Product.slug.ilike(needle),
                    Product.brand.ilike(needle),
                    translated_match,
                    variant_match,
                ),
            )
            .order_by(Product.updated_at.desc())
            .limit(30)
        )
    ).scalars().all()
    items = []
    preset_data = await load_size_preset_data(session)
    for product in products:
        translations = (
            await session.execute(
                select(ProductTranslation).where(ProductTranslation.product_id == product.id)
            )
        ).scalars().all()
        by_locale = {translation.locale: translation.name for translation in translations}
        variants = (
            await session.execute(
                select(ProductVariant).where(
                    ProductVariant.product_id == product.id,
                    ProductVariant.is_active.is_(True),
                ).order_by(ProductVariant.sku).limit(50)
            )
        ).scalars().all()
        category = await session.get(Category, product.category_id)
        variants = [
            variant for variant in variants
            if category and size_variant_is_visible(
                category.department, variant.option_values, preset_data
            )
        ]
        if not variants:
            continue
        items.append(
            {
                "id": product.id,
                "slug": product.slug,
                "brand": product.brand,
                "name": by_locale.get(locale) or by_locale.get("en") or by_locale.get("id") or product.slug,
                "image_url": _media_url(product, variants[0]),
                "currency": product.currency,
                "variants": [
                    {
                        "id": variant.id,
                        "sku": variant.sku,
                        "option_values": variant.option_values or {},
                        "option_label": _option_label(variant.option_values or {}),
                        "unit_price": _price(product, variant),
                    }
                    for variant in variants
                ],
            }
        )
    return {"items": items}


@router.post("/{conversation_id}/candidates", status_code=201)
async def create_candidate(
    conversation_id: str,
    payload: CandidateCreateIn,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    conversation = await _load_conversation(session, conversation_id)
    connection = await _reply_context(session, conversation)
    # Serialize candidate selection against a preset rollout. Otherwise an
    # admin could pick a legacy size just as the bulk apply hides it.
    preset_data = await load_size_preset_data(session, shared_lock=True)
    product = await session.get(Product, payload.product_id)
    variant = await session.get(ProductVariant, payload.variant_id)
    category = await session.get(Category, product.category_id) if product else None
    if (
        not product
        or product.status != "active"
        or product.is_demo
        or not variant
        or variant.product_id != product.id
        or not variant.is_active
        or not category
        or not size_variant_is_visible(
            category.department, variant.option_values, preset_data
        )
    ):
        raise _error(409, "catalog_item_unavailable")
    source_message = None
    if payload.source_message_id:
        source_message = await session.scalar(
            select(TelegramInboxMessage).where(
                TelegramInboxMessage.id == payload.source_message_id,
                TelegramInboxMessage.conversation_id == conversation.id,
                TelegramInboxMessage.direction == "inbound",
            )
        )
        if not source_message:
            raise _error(404, "source_message_not_found")
    translation = await session.scalar(
        select(ProductTranslation).where(
            ProductTranslation.product_id == product.id,
            ProductTranslation.locale == conversation.locale,
        )
    )
    if not translation:
        translation = await session.scalar(
            select(ProductTranslation).where(
                ProductTranslation.product_id == product.id,
                ProductTranslation.locale == "en",
            )
        )
    product_name = (translation.name if translation else product.slug)[:255]
    image_url = _media_url(product, variant)
    token = secrets.token_urlsafe(12)
    candidate = TelegramProductCandidate(
        conversation_id=conversation.id,
        source_message_id=source_message.id if source_message else None,
        product_id=product.id,
        variant_id=variant.id,
        sku=variant.sku,
        product_name=product_name,
        option_values=variant.option_values or {},
        image_url=image_url,
        quantity=payload.quantity,
        status="pending",
        callback_token=token,
    )
    session.add(candidate)
    await session.commit()
    caption = candidate_copy(conversation.locale, product_name, variant.sku, payload.quantity)
    markup = candidate_keyboard(token, conversation.locale)
    try:
        if image_url and image_url.startswith(("https://", "http://")):
            result = await bot_request(
                TELEGRAM_BOT_TOKEN,
                "sendPhoto",
                {
                    "business_connection_id": connection.connection_id,
                    "chat_id": conversation.chat_id,
                    "photo": image_url,
                    "caption": caption[:1024],
                    "reply_markup": markup,
                },
            )
            message_type = "photo"
        else:
            result = await bot_request(
                TELEGRAM_BOT_TOKEN,
                "sendMessage",
                {
                    "business_connection_id": connection.connection_id,
                    "chat_id": conversation.chat_id,
                    "text": caption,
                    "reply_markup": markup,
                },
            )
            message_type = "text"
    except TimeoutError as exc:
        candidate = await session.scalar(
            select(TelegramProductCandidate)
            .where(TelegramProductCandidate.id == candidate.id)
            .with_for_update()
        )
        if candidate and candidate.status == "pending":
            candidate.status = "send_unknown"
        await session.commit()
        raise _error(502, "candidate_delivery_unknown") from exc
    except TelegramDeliveryError as exc:
        candidate = await session.scalar(
            select(TelegramProductCandidate)
            .where(TelegramProductCandidate.id == candidate.id)
            .with_for_update()
        )
        if candidate and candidate.status == "pending":
            candidate.status = "send_failed"
        await session.commit()
        raise _error(502, "candidate_send_failed") from exc
    candidate.confirmation_message_id = result.get("message_id")
    await _save_cms_message(session, conversation, result, caption, message_type)
    await audit(session, user.id, "admin.telegram_inbox.candidate.send", "telegram_product_candidate", candidate.id, {"sku": variant.sku})
    await session.commit()
    return {"id": candidate.id, "status": candidate.status, "confirmation_message_id": candidate.confirmation_message_id}


@router.patch("/{conversation_id}/candidates/{candidate_id}")
async def review_candidate(
    conversation_id: str,
    candidate_id: str,
    payload: CandidateReviewIn,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    conversation = await _load_conversation(session, conversation_id)
    candidate = await session.scalar(
        select(TelegramProductCandidate)
        .where(
            TelegramProductCandidate.id == candidate_id,
            TelegramProductCandidate.conversation_id == conversation.id,
        )
        .with_for_update()
    )
    if not candidate:
        raise _error(404, "candidate_not_found")
    if candidate.status not in {"pending", "send_unknown"}:
        raise _error(409, "candidate_already_reviewed")
    candidate.status = payload.status
    candidate.confirmation_source = "admin"
    candidate.confirmed_at = utcnow() if payload.status == "confirmed" else None
    confirmed = await session.scalar(
        select(TelegramProductCandidate.id).where(
            TelegramProductCandidate.conversation_id == conversation.id,
            TelegramProductCandidate.status == "confirmed",
        ).limit(1)
    )
    if payload.status == "confirmed" or confirmed:
        conversation.status = "ready_for_order"
    elif conversation.status != "archived":
        conversation.status = "needs_admin"
    await audit(session, user.id, "admin.telegram_inbox.candidate.review", "telegram_product_candidate", candidate.id, {"status": payload.status})
    await session.commit()
    return {"id": candidate.id, "status": candidate.status, "confirmation_source": candidate.confirmation_source}


@router.post("/{conversation_id}/orders", status_code=201)
async def create_order_from_conversation(
    conversation_id: str,
    payload: InboxOrderCreateIn,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    conversation = await _load_conversation(session, conversation_id)
    # Keep the catalog visibility rule stable until this order transaction
    # commits, using the same preset-first lock order as cart additions.
    preset_data = await load_size_preset_data(session, shared_lock=True)
    if not payload.shipping_address.get("recipient_name") or not payload.shipping_address.get("phone"):
        raise _error(422, "shipping_recipient_required")
    if idempotency_key is not None and not 16 <= len(idempotency_key) <= 80:
        raise _error(422, "invalid_idempotency_key")
    candidate_ids = list(dict.fromkeys(payload.candidate_ids))
    if len(candidate_ids) != len(payload.candidate_ids):
        raise _error(422, "duplicate_candidate")
    candidates = (
        await session.execute(
            select(TelegramProductCandidate)
            .where(
                TelegramProductCandidate.conversation_id == conversation.id,
                TelegramProductCandidate.id.in_(candidate_ids),
                TelegramProductCandidate.status == "confirmed",
                TelegramProductCandidate.order_id.is_(None),
            )
            .with_for_update()
        )
    ).scalars().all()
    if len(candidates) != len(candidate_ids):
        raise _error(409, "only_confirmed_candidates_can_be_ordered")
    if idempotency_key:
        existing = await session.scalar(select(Order).where(Order.idempotency_key == idempotency_key))
        if existing:
            if existing.telegram_conversation_id != conversation.id:
                raise _error(409, "idempotency_key_conflict")
            return {"order_number": existing.order_number, "order_id": existing.id, "status": existing.status}

    order_lines = []
    subtotal = 0
    currencies = set()
    for candidate in candidates:
        product = await session.get(Product, candidate.product_id)
        variant = await session.get(ProductVariant, candidate.variant_id)
        category = await session.get(Category, product.category_id) if product else None
        if (
            not product
            or product.status != "active"
            or product.is_demo
            or not variant
            or variant.product_id != product.id
            or not variant.is_active
            or not category
            or not size_variant_is_visible(
                category.department, variant.option_values, preset_data
            )
        ):
            raise _error(409, "catalog_item_unavailable", sku=candidate.sku)
        unit_price = _price(product, variant)
        line_total = unit_price * candidate.quantity
        subtotal += line_total
        currencies.add(product.currency)
        order_lines.append((candidate, product, variant, unit_price, line_total))
    if len(currencies) != 1:
        raise _error(409, "mixed_currency_order_unsupported")

    order_number = f"MC-{uuid.uuid4().hex[:10].upper()}"
    order = Order(
        order_number=order_number,
        guest_email=payload.guest_email,
        guest_access_token=secrets.token_urlsafe(24),
        shipping_address=payload.shipping_address,
        shipping_method=payload.shipping_method,
        subtotal=subtotal,
        shipping_amount=payload.shipping_amount,
        grand_total=subtotal + payload.shipping_amount,
        currency=next(iter(currencies)),
        payment_state="unpaid",
        status="pending_payment",
        idempotency_key=idempotency_key,
        order_source="telegram_inbox",
        fulfillment_mode="pre_order",
        telegram_conversation_id=conversation.id,
    )
    session.add(order)
    await session.flush()
    for candidate, product, variant, unit_price, line_total in order_lines:
        session.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                variant_id=variant.id,
                seller_id=product.seller_id,
                sku=variant.sku,
                product_name=candidate.product_name,
                option_values=candidate.option_values or {},
                image_url=candidate.image_url,
                unit_price=unit_price,
                quantity=candidate.quantity,
                line_total=line_total,
            )
        )
        candidate.status = "ordered"
        candidate.order_id = order.id
    session.add(
        Payment(
            order_id=order.id,
            provider="manual_transfer",
            environment=APP_ENV,
            currency=order.currency,
            amount=order.grand_total,
            status="pending",
            merchant_trans_id=f"MANUAL-{uuid.uuid4().hex[:20].upper()}",
        )
    )
    conversation.status = "waiting_customer"
    conversation.last_message_at = utcnow()
    await audit(
        session,
        user.id,
        "admin.telegram_inbox.order.create",
        "order",
        order.order_number,
        {"conversation_id": conversation.id, "candidate_ids": candidate_ids},
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if idempotency_key:
            existing = await session.scalar(
                select(Order).where(Order.idempotency_key == idempotency_key)
            )
            if existing and existing.telegram_conversation_id == conversation.id:
                return {"order_number": existing.order_number, "order_id": existing.id, "status": existing.status}
        raise _error(409, "order_creation_conflict") from exc

    # Reuse the same manual-transfer notification workflow as website inquiries.
    from routers.manual_orders import _send_payment_prompt

    await _send_payment_prompt(order.order_number, session)
    return {"order_number": order.order_number, "order_id": order.id, "status": order.status}
