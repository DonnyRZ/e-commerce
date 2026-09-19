"""Telegram Business cart-inquiry endpoints and webhook receiver."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import re
import secrets
import time
from datetime import timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth import csrf_protect
from config import (
    FRONTEND_URL,
    RATE_LIMIT_BACKEND,
    SUPPORTED_LOCALES,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_BOT_USERNAME,
    TELEGRAM_INQUIRIES_ENABLED,
    TELEGRAM_INQUIRY_TTL_DAYS,
    TELEGRAM_STORE_USERNAME,
    TELEGRAM_WEBHOOK_SECRET,
)
from db.models import (
    TelegramBusinessConnection,
    TelegramCartInquiry,
    TelegramUpdateReceipt,
    utcnow,
)
from db.session import SessionLocal, get_session
from rate_limit import enforce_redis_limit
from routers.shop import _cart_payload, _find_cart, _optional_user
from telegram_inquiries import (
    TelegramDeliveryError,
    bot_request,
    make_snapshot,
    localized,
    prefilled_message,
    send_inquiry,
    telegram_webhook_is_ready,
)

router = APIRouter(prefix="/api/v1/telegram", tags=["telegram-inquiries"])
logger = logging.getLogger("muslimah_cantik.telegram")
REFERENCE_RE = re.compile(r"\bSC-[A-F0-9]{32}\b", re.IGNORECASE)
_memory_windows: dict[str, tuple[float, int]] = {}
_memory_lock = asyncio.Lock()
_webhook_health_cache: tuple[float, bool] | None = None
_webhook_health_lock = asyncio.Lock()


class InquiryRequest(BaseModel):
    locale: str = Field(default="en", min_length=2, max_length=5)


def _normalized_username(value: str) -> str:
    return value.strip().lstrip("@").casefold()


def _configuration_ready() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_WEBHOOK_SECRET)


async def _expire_old_snapshots(session: AsyncSession) -> None:
    now = utcnow()
    await session.execute(
        update(TelegramCartInquiry)
        .where(
            TelegramCartInquiry.expires_at <= now,
            TelegramCartInquiry.status.in_(["pending", "sending", "sent"]),
        )
        .values(status="expired", snapshot=None)
    )
    await session.execute(
        delete(TelegramUpdateReceipt).where(
            TelegramUpdateReceipt.received_at < now - timedelta(days=30)
        )
    )
    await session.commit()


async def telegram_inquiry_cleanup_loop() -> None:
    """Clear expired snapshots periodically, even when the cart is idle."""
    while True:
        await asyncio.sleep(60 * 60)
        try:
            async with SessionLocal() as session:
                await _expire_old_snapshots(session)
        except Exception:
            logger.warning("Telegram inquiry retention cleanup failed")


async def _ready_connection(session: AsyncSession) -> TelegramBusinessConnection | None:
    return await session.scalar(
        select(TelegramBusinessConnection)
        .where(
            TelegramBusinessConnection.username == _normalized_username(TELEGRAM_STORE_USERNAME),
            TelegramBusinessConnection.is_enabled.is_(True),
            TelegramBusinessConnection.can_reply.is_(True),
            TelegramBusinessConnection.can_read_messages.is_(True),
        )
        .order_by(TelegramBusinessConnection.updated_at.desc())
        .limit(1)
    )


async def _webhook_ready() -> bool:
    global _webhook_health_cache
    now = time.monotonic()
    if _webhook_health_cache and now - _webhook_health_cache[0] < 30:
        return _webhook_health_cache[1]
    async with _webhook_health_lock:
        now = time.monotonic()
        if _webhook_health_cache and now - _webhook_health_cache[0] < 30:
            return _webhook_health_cache[1]
        expected_url = f"{FRONTEND_URL.rstrip('/')}/api/v1/telegram/webhook"
        healthy = await telegram_webhook_is_ready(TELEGRAM_BOT_TOKEN, expected_url)
        _webhook_health_cache = (time.monotonic(), healthy)
        return healthy


async def _status(session: AsyncSession) -> dict:
    configuration_ready = _configuration_ready()
    connection = (
        await _ready_connection(session)
        if TELEGRAM_INQUIRIES_ENABLED and configuration_ready
        else None
    )
    business_ready = connection is not None
    webhook_ready = (
        await _webhook_ready()
        if TELEGRAM_INQUIRIES_ENABLED and configuration_ready and business_ready
        else None
    )
    reason = None
    if not TELEGRAM_INQUIRIES_ENABLED:
        reason = "feature_disabled"
    elif not configuration_ready:
        reason = "configuration_incomplete"
    elif not business_ready:
        reason = "business_connection_missing"
    elif not webhook_ready:
        reason = "webhook_unavailable"
    return {
        "available": reason is None,
        "configuration_ready": configuration_ready,
        "business_connection_ready": business_ready,
        "webhook_ready": webhook_ready,
        "store_username": _normalized_username(TELEGRAM_STORE_USERNAME),
        "bot_username": _normalized_username(TELEGRAM_BOT_USERNAME),
        "reason": reason,
    }


async def _limit_inquiry(cart_id: str) -> None:
    identity = hashlib.sha256(f"cart:{cart_id}".encode()).hexdigest()
    if RATE_LIMIT_BACKEND == "redis":
        await enforce_redis_limit(
            "telegram-cart-inquiry", identity, limit=5, window_seconds=600
        )
        return
    now = time.monotonic()
    async with _memory_lock:
        if len(_memory_windows) > 5000:
            expired = [key for key, (started, _) in _memory_windows.items() if now - started >= 600]
            for key in expired:
                _memory_windows.pop(key, None)
        start, count = _memory_windows.get(identity, (now, 0))
        if now - start >= 600:
            start, count = now, 0
        if count >= 5:
            raise HTTPException(status_code=429, detail="too_many_requests")
        _memory_windows[identity] = (start, count + 1)


@router.get("/status")
async def telegram_status(session: AsyncSession = Depends(get_session)):
    # A disabled optional integration must not make the status endpoint depend
    # on integration-only tables being migrated.
    if TELEGRAM_INQUIRIES_ENABLED:
        await _expire_old_snapshots(session)
    return await _status(session)


@router.post("/inquiries", status_code=201)
async def create_inquiry(
    payload: InquiryRequest,
    request: Request,
    guest: bool = False,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    status = await _status(session)
    if not status["available"]:
        raise HTTPException(status_code=503, detail={"error": "telegram_inquiry_unavailable"})
    if payload.locale not in SUPPORTED_LOCALES:
        raise HTTPException(status_code=422, detail="unsupported_locale")
    if not idempotency_key or not 16 <= len(idempotency_key) <= 80:
        raise HTTPException(status_code=422, detail="invalid_idempotency_key")

    user = None if guest else await _optional_user(request, session)
    cart = await _find_cart(request, session, user)
    cart_payload = await _cart_payload(session, cart)
    if not cart or not cart_payload["items"]:
        raise HTTPException(status_code=400, detail={"error": "cart_empty"})
    await _limit_inquiry(cart.id)
    await _expire_old_snapshots(session)

    existing = await session.scalar(
        select(TelegramCartInquiry).where(
            TelegramCartInquiry.cart_id == cart.id,
            TelegramCartInquiry.idempotency_key == idempotency_key,
        )
    )
    if existing:
        if existing.status == "expired" or existing.expires_at <= utcnow():
            raise HTTPException(status_code=409, detail="inquiry_key_already_used")
        reference = existing.reference
        expires_at = existing.expires_at
        link_locale = existing.locale
    else:
        reference = f"SC-{secrets.token_hex(16).upper()}"
        expires_at = utcnow() + timedelta(days=TELEGRAM_INQUIRY_TTL_DAYS)
        inquiry = TelegramCartInquiry(
            reference=reference,
            cart_id=cart.id,
            user_id=user.id if user else None,
            idempotency_key=idempotency_key,
            locale=payload.locale,
            snapshot=make_snapshot(cart_payload, payload.locale),
            status="pending",
            expires_at=expires_at,
        )
        session.add(inquiry)
        try:
            await session.commit()
            link_locale = payload.locale
        except IntegrityError:
            await session.rollback()
            existing = await session.scalar(
                select(TelegramCartInquiry).where(
                    TelegramCartInquiry.cart_id == cart.id,
                    TelegramCartInquiry.idempotency_key == idempotency_key,
                )
            )
            if not existing or existing.status != "pending":
                raise HTTPException(status_code=409, detail="inquiry_key_already_used")
            reference = existing.reference
            expires_at = existing.expires_at
            link_locale = existing.locale

    message = prefilled_message(link_locale, reference)
    store_username = _normalized_username(TELEGRAM_STORE_USERNAME)
    telegram_url = f"https://t.me/{store_username}?{urlencode({'text': message})}"
    return {
        "reference": reference,
        "telegram_url": telegram_url,
        "expires_at": expires_at.isoformat(),
    }


async def _claim_update(session: AsyncSession, update_id: int) -> bool:
    receipt = await session.scalar(
        select(TelegramUpdateReceipt)
        .where(TelegramUpdateReceipt.update_id == update_id)
        .with_for_update()
    )
    if receipt:
        if receipt.status != "failed":
            return False
        receipt.status = "processing"
        await session.commit()
        return True
    session.add(TelegramUpdateReceipt(update_id=update_id, status="processing"))
    try:
        await session.commit()
        return True
    except IntegrityError:
        await session.rollback()
        return False


async def _store_connection(session: AsyncSession, payload: dict) -> None:
    connection_id = payload.get("id")
    if not isinstance(connection_id, str) or not connection_id or len(connection_id) > 255:
        return
    user = payload.get("user") if isinstance(payload.get("user"), dict) else {}
    rights = payload.get("rights") if isinstance(payload.get("rights"), dict) else {}
    username = str(user.get("username") or "").lstrip("@").lower()[:32]
    row = await session.get(TelegramBusinessConnection, connection_id)
    if row is None:
        row = TelegramBusinessConnection(connection_id=connection_id)
        session.add(row)
    row.business_user_id = str(user.get("id") or "")[:32]
    row.username = username
    row.is_enabled = bool(payload.get("is_enabled"))
    row.can_reply = bool(rights.get("can_reply"))
    row.can_read_messages = bool(rights.get("can_read_messages"))
    row.updated_at = utcnow()
    await session.commit()


async def _send_expired(connection_id: str, chat_id: int, locale: str) -> None:
    await bot_request(
        TELEGRAM_BOT_TOKEN,
        "sendMessage",
        {
            "business_connection_id": connection_id,
            "chat_id": chat_id,
            "text": localized(locale, "expired"),
        },
    )


async def _handle_business_message(session: AsyncSession, message: dict) -> None:
    connection_id = message.get("business_connection_id")
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    sender = message.get("from") if isinstance(message.get("from"), dict) else {}
    if not isinstance(connection_id, str) or chat.get("type") != "private":
        return
    connection = await session.get(TelegramBusinessConnection, connection_id)
    if (
        not connection
        or not connection.is_enabled
        or connection.username != _normalized_username(TELEGRAM_STORE_USERNAME)
        or not connection.can_reply
        or not connection.can_read_messages
        or str(sender.get("id") or "") == connection.business_user_id
        or sender.get("is_bot")
    ):
        return
    chat_id = chat.get("id")
    if not isinstance(chat_id, int) or isinstance(chat_id, bool):
        return
    text = message.get("text") or message.get("caption") or ""
    match = REFERENCE_RE.search(text) if isinstance(text, str) else None
    if not match:
        return
    reference = match.group(0).upper()
    inquiry = await session.scalar(
        select(TelegramCartInquiry)
        .where(TelegramCartInquiry.reference == reference)
        .with_for_update()
    )
    if not inquiry:
        return
    if inquiry.status == "expired" or inquiry.expires_at <= utcnow():
        locale = inquiry.locale
        if inquiry.status != "expired":
            inquiry.status = "expired"
            inquiry.snapshot = None
            await session.commit()
        try:
            await _send_expired(connection_id, chat_id, locale)
        except (TelegramDeliveryError, TimeoutError):
            pass
        return
    if inquiry.status != "pending" or not isinstance(inquiry.snapshot, dict):
        return

    # Keep the Business chat mapping so admin order updates can notify the
    # same customer later. The chat id is never exposed to the storefront.
    inquiry.telegram_connection_id = connection_id
    inquiry.telegram_chat_id = chat_id
    snapshot = inquiry.snapshot
    inquiry.status = "sending"
    await session.commit()
    try:
        await send_inquiry(
            TELEGRAM_BOT_TOKEN, connection_id, chat_id, snapshot, reference
        )
    except TimeoutError:
        # Telegram may have accepted the request before the network timed out.
        # Keep this update claimed; retrying it could send a duplicate carousel.
        return
    except TelegramDeliveryError:
        inquiry.status = "pending"
        await session.commit()
        raise
    inquiry.status = "sent"
    inquiry.delivered_at = utcnow()
    await session.commit()


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    secret_header: str | None = Header(
        default=None, alias="X-Telegram-Bot-Api-Secret-Token"
    ),
    session: AsyncSession = Depends(get_session),
):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=404, detail="not_found")
    if not secret_header or not hmac.compare_digest(secret_header, TELEGRAM_WEBHOOK_SECRET):
        raise HTTPException(status_code=403, detail="invalid_webhook_secret")
    body = await request.body()
    if len(body) > 512 * 1024:
        raise HTTPException(status_code=413, detail="payload_too_large")
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_json") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid_update")
    update_id = payload.get("update_id")
    if not isinstance(update_id, int) or isinstance(update_id, bool) or update_id < 0:
        raise HTTPException(status_code=400, detail="invalid_update_id")
    await _expire_old_snapshots(session)
    if not await _claim_update(session, update_id):
        return {"ok": True, "duplicate": True}

    try:
        connection_update = payload.get("business_connection")
        if isinstance(connection_update, dict):
            await _store_connection(session, connection_update)
        business_message = payload.get("business_message")
        if TELEGRAM_INQUIRIES_ENABLED and isinstance(business_message, dict):
            await _handle_business_message(session, business_message)
        receipt = await session.get(TelegramUpdateReceipt, update_id)
        if receipt:
            receipt.status = "processed"
            await session.commit()
        return {"ok": True}
    except TelegramDeliveryError as exc:
        await session.rollback()
        receipt = await session.get(TelegramUpdateReceipt, update_id)
        if receipt:
            receipt.status = "failed"
            await session.commit()
        logger.warning("Telegram inquiry delivery failed; update will be retried")
        raise HTTPException(status_code=503, detail="telegram_delivery_failed") from exc
    except Exception as exc:
        # Avoid logging the update body, message text, or Bot API URL/token.
        await session.rollback()
        receipt = await session.get(TelegramUpdateReceipt, update_id)
        if receipt:
            receipt.status = "failed"
            await session.commit()
        logger.error("Telegram webhook processing failed")
        raise HTTPException(status_code=503, detail="telegram_webhook_processing_failed") from exc
