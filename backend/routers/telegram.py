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
from sqlalchemy import delete, func, select, update
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
    Cart,
    CartItem,
    Order,
    OrderItem,
    Payment,
    PaymentDestination,
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
from payment_destinations import (
    answer_locale_error,
    payment_choice_keyboard,
    payment_detail_keyboard,
    payment_detail_text,
    payment_locale,
    payment_prompt_text,
)

router = APIRouter(prefix="/api/v1/telegram", tags=["telegram-inquiries"])
logger = logging.getLogger("muslimah_cantik.telegram")
REFERENCE_RE = re.compile(r"\bSC-[A-F0-9]{32}\b", re.IGNORECASE)
PAYMENT_CALLBACK_RE = re.compile(
    r"^(?P<action>bank|back):(?P<token>[A-Za-z0-9_-]{16,24})(?::(?P<key>[a-fA-F0-9]{8}))?(?::(?P<locale>id|en|uz|ru))?$"
)
_memory_windows: dict[str, tuple[float, int]] = {}
_memory_lock = asyncio.Lock()
_webhook_health_cache: tuple[float, bool] | None = None
_webhook_health_lock = asyncio.Lock()


class InquiryRequest(BaseModel):
    locale: str = Field(default="en", min_length=2, max_length=5)


def _normalized_username(value: str) -> str:
    return value.strip().lstrip("@").casefold()


async def _remove_submitted_cart_quantities(
    session: AsyncSession, cart_id: str, items: list[dict]
) -> None:
    """Remove only quantities included in the successfully sent inquiry."""
    cart = await session.scalar(
        select(Cart).where(Cart.id == cart_id).with_for_update()
    )
    if not cart:
        return
    for snapshot_item in items:
        item_id = snapshot_item.get("_cart_item_id")
        quantity = snapshot_item.get("quantity")
        if not isinstance(item_id, str) or not item_id or not isinstance(quantity, int) or quantity <= 0:
            continue
        row = await session.scalar(
            select(CartItem)
            .where(
                CartItem.id == item_id,
                CartItem.cart_id == cart.id,
                CartItem.product_id == snapshot_item.get("_cart_product_id"),
                CartItem.variant_id == snapshot_item.get("_cart_variant_id"),
            )
            .with_for_update()
        )
        if not row:
            continue
        remaining = max(int(row.quantity or 0) - quantity, 0)
        if remaining:
            row.quantity = remaining
        else:
            await session.delete(row)


def _configuration_ready() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_WEBHOOK_SECRET)


async def _expire_old_snapshots(session: AsyncSession) -> None:
    now = utcnow()
    await session.execute(
        update(TelegramCartInquiry)
        .where(
            TelegramCartInquiry.expires_at <= now,
            TelegramCartInquiry.status.in_(["pending", "sending", "sent", "unknown"]),
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


@router.get("/inquiries/{reference}")
async def inquiry_status(reference: str, request: Request, guest: bool = False,
                         session: AsyncSession = Depends(get_session)):
    user = None if guest else await _optional_user(request, session)
    cart = await _find_cart(request, session, user)
    row = await session.scalar(select(TelegramCartInquiry).where(
        TelegramCartInquiry.reference == reference,
        TelegramCartInquiry.cart_id == (cart.id if cart else ""),
    ))
    if not row:
        raise HTTPException(status_code=404, detail="inquiry_not_found")
    state = row.status
    if row.expires_at <= utcnow() and state != "order_created":
        state = "expired"
    elif state == "sending" and time.time() - (row.snapshot or {}).get("_delivery", {}).get("started", 0) >= 300:
        state = "unknown"
    return {"reference": row.reference, "status": state, "expires_at": row.expires_at.isoformat()}


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
    if not cart:
        raise HTTPException(status_code=400, detail={"error": "cart_empty"})
    # Serialize snapshot creation with cart mutations and concurrent retries.
    await session.scalar(select(Cart).where(Cart.id == cart.id).with_for_update())

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
        await _limit_inquiry(cart.id)
        cart_payload = await _cart_payload(session, cart)
        if not cart_payload["items"]:
            raise HTTPException(status_code=400, detail={"error": "cart_empty"})
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
        "message": message,
        "expires_at": expires_at.isoformat(),
    }


async def _claim_update(session: AsyncSession, update_id: int) -> bool:
    receipt = await session.scalar(
        select(TelegramUpdateReceipt)
        .where(TelegramUpdateReceipt.update_id == update_id)
        .with_for_update()
    )
    if receipt:
        stale = receipt.status == "processing" and receipt.received_at < utcnow() - timedelta(minutes=5)
        if receipt.status == "processing" and not stale:
            # Do not acknowledge an unfinished update: if its worker crashes,
            # Telegram must still retry after the lease expires.
            raise HTTPException(status_code=503, detail="telegram_update_in_progress")
        if receipt.status != "failed" and not stale:
            return False
        receipt.status = "processing"
        receipt.received_at = utcnow()
        await session.commit()
        return True
    session.add(TelegramUpdateReceipt(update_id=update_id, status="processing"))
    try:
        await session.commit()
        return True
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=503, detail="telegram_update_in_progress")


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


async def _handle_business_message(session: AsyncSession, message: dict, update_id: int | None = None) -> None:
    connection_id = message.get("business_connection_id")
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    sender = message.get("from") if isinstance(message.get("from"), dict) else {}
    if not isinstance(connection_id, str) or chat.get("type") != "private":
        return
    connection = await session.get(TelegramBusinessConnection, connection_id)
    if connection is None:
        # Connection updates can arrive out of order or be missed during a restart.
        details = await bot_request(TELEGRAM_BOT_TOKEN, "getBusinessConnection", {"business_connection_id": connection_id})
        if details.get("id") != connection_id:
            raise TelegramDeliveryError("business_connection_unavailable")
        await _store_connection(session, details)
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
        logger.info("business message ignored: connection_or_sender_not_eligible")
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
        logger.info("inquiry ignored: reference_not_found")
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
    if not isinstance(inquiry.snapshot, dict):
        return
    # Never allow a leaked reference to move an already bound inquiry to another chat.
    if inquiry.telegram_chat_id is not None and (
        inquiry.telegram_chat_id != chat_id or inquiry.telegram_connection_id != connection_id
    ):
        logger.warning("inquiry ignored: chat_mismatch")
        return
    delivery = inquiry.snapshot.get("_delivery", {})
    if inquiry.status == "sending":
        if time.time() - delivery.get("started", 0) < 300:
            return
        inquiry.status = "unknown"
    if inquiry.status == "unknown" and delivery.get("update_id") == update_id:
        # A redelivery of the original update cannot establish whether a send succeeded.
        await session.commit()
        return
    if inquiry.status not in ("pending", "unknown"):
        logger.info("inquiry ignored: status=%s", inquiry.status)
        return

    # Keep the Business chat mapping so admin order updates can notify the
    # same customer later. The chat id is never exposed to the storefront.
    inquiry.telegram_connection_id = connection_id
    inquiry.telegram_chat_id = chat_id
    snapshot = {**inquiry.snapshot, "_delivery": {"started": time.time(), "update_id": update_id}}
    inquiry.snapshot = snapshot
    inquiry.status = "sending"
    await session.commit()
    try:
        await send_inquiry(
            TELEGRAM_BOT_TOKEN, connection_id, chat_id, snapshot, reference
        )
    except TimeoutError:
        # Telegram may have accepted the request before the network timed out.
        # Keep this update claimed; retrying it could send a duplicate carousel.
        inquiry.status = "unknown"
        await session.commit()
        logger.warning("inquiry delivery outcome unknown; awaiting explicit customer retry")
        return
    except TelegramDeliveryError:
        inquiry.status = "pending"
        await session.commit()
        raise
    inquiry.status = "sent"
    inquiry.delivered_at = utcnow()
    await _remove_submitted_cart_quantities(
        session, inquiry.cart_id, snapshot.get("items", [])
    )
    await session.commit()


async def _answer_payment_callback(
    callback_query: dict, text: str | None = None, *, show_alert: bool = False
) -> None:
    callback_id = callback_query.get("id")
    if not isinstance(callback_id, str) or not callback_id or not TELEGRAM_BOT_TOKEN:
        return
    payload: dict[str, object] = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text[:190]
        payload["show_alert"] = show_alert
    try:
        await bot_request(TELEGRAM_BOT_TOKEN, "answerCallbackQuery", payload)
    except (TelegramDeliveryError, TimeoutError):
        # The state change is persisted independently; Telegram can still
        # deliver the callback update again if its acknowledgement failed.
        return


async def _edit_payment_message(
    connection_id: str,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: dict,
) -> None:
    try:
        await bot_request(
            TELEGRAM_BOT_TOKEN,
            "editMessageText",
            {
                "business_connection_id": connection_id,
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text[:3900],
                "reply_markup": reply_markup,
            },
        )
    except TelegramDeliveryError as exc:
        if exc.safe_code != "message_not_modified":
            raise


async def _refresh_payment_prompt(
    session: AsyncSession, payment: Payment, order: Order, inquiry: TelegramCartInquiry
) -> None:
    destinations = (
        await session.execute(
            select(PaymentDestination)
            .where(PaymentDestination.is_active.is_(True))
            .order_by(PaymentDestination.slot)
        )
    ).scalars().all()
    item_count = await session.scalar(
        select(func.coalesce(func.sum(OrderItem.quantity), 0)).where(
            OrderItem.order_id == order.id
        )
    )
    tracking_link = (
        f"{FRONTEND_URL}/orders/track?order_number={order.order_number}&token={order.guest_access_token}"
        if order.guest_access_token
        else f"{FRONTEND_URL}/orders/{order.order_number}"
    )
    text = (
        payment_prompt_text(order, int(item_count or 0), inquiry.locale, tracking_link)
        if destinations
        else answer_locale_error(inquiry.locale, "no_destinations")
    )
    await _edit_payment_message(
        inquiry.telegram_connection_id,
        inquiry.telegram_chat_id,
        payment.telegram_payment_message_id,
        text,
        payment_choice_keyboard(
            destinations, payment.telegram_selection_token, inquiry.locale
        ),
    )


async def _handle_payment_callback(
    session: AsyncSession, callback_query: dict
) -> None:
    data = callback_query.get("data")
    match = PAYMENT_CALLBACK_RE.fullmatch(data) if isinstance(data, str) else None
    if not match:
        await _answer_payment_callback(callback_query)
        return

    token = match.group("token")
    callback_locale = match.group("locale") or "id"
    payment = await session.scalar(
        select(Payment)
        .where(Payment.telegram_selection_token == token)
        .with_for_update()
    )
    message = callback_query.get("message")
    message = message if isinstance(message, dict) else {}
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    sender = (
        callback_query.get("from")
        if isinstance(callback_query.get("from"), dict)
        else {}
    )
    chat_id = chat.get("id")
    message_id = message.get("message_id")
    if (
        not payment
        or not isinstance(chat_id, int)
        or isinstance(chat_id, bool)
        or chat.get("type") != "private"
        or not isinstance(sender.get("id"), int)
        or sender.get("id") != chat_id
        or not isinstance(message_id, int)
        or isinstance(message_id, bool)
    ):
        await _answer_payment_callback(
            callback_query,
            answer_locale_error(payment_locale(callback_locale), "invalid"),
            show_alert=True,
        )
        return

    order = await session.scalar(
        select(Order).where(Order.id == payment.order_id).with_for_update()
    )
    inquiry = await session.scalar(
        select(TelegramCartInquiry).where(TelegramCartInquiry.order_id == payment.order_id)
    )
    if (
        not order
        or not inquiry
        or not inquiry.telegram_connection_id
        or inquiry.telegram_chat_id != chat_id
        or (
            message.get("business_connection_id")
            and message["business_connection_id"] != inquiry.telegram_connection_id
        )
        or (
            payment.telegram_payment_message_id is not None
            and payment.telegram_payment_message_id != message_id
        )
    ):
        await _answer_payment_callback(
            callback_query, answer_locale_error("id", "invalid"), show_alert=True
        )
        return

    locale = payment_locale(inquiry.locale)
    if order.status != "pending_payment" or payment.status != "pending":
        await _answer_payment_callback(
            callback_query, answer_locale_error(locale, "locked"), show_alert=True
        )
        try:
            await _edit_payment_message(
                inquiry.telegram_connection_id,
                chat_id,
                message_id,
                answer_locale_error(locale, "locked"),
                {"inline_keyboard": []},
            )
        except (TelegramDeliveryError, TimeoutError):
            pass
        return

    if payment.telegram_payment_message_id is None:
        # A customer can tap as soon as Telegram renders the keyboard, before
        # the sendMessage HTTP response has been committed by the API process.
        payment.telegram_payment_message_id = message_id

    action = match.group("action")
    if action == "bank":
        destination = await session.scalar(
            select(PaymentDestination).where(
                PaymentDestination.callback_key == match.group("key"),
                PaymentDestination.is_active.is_(True),
            ).with_for_update()
        )
        if not destination:
            await session.commit()
            await _answer_payment_callback(
                callback_query,
                answer_locale_error(locale, "unavailable"),
                show_alert=True,
            )
            await _refresh_payment_prompt(session, payment, order, inquiry)
            return
        snapshot = {
            "bank_name": destination.bank_name,
            "destination_type": destination.destination_type,
            "account_number": destination.account_number,
            "holder_name": destination.holder_name,
        }
        payment.destination_id = destination.id
        payment.destination_snapshot = snapshot
        await session.commit()
        await _answer_payment_callback(
            callback_query, answer_locale_error(locale, "selected")
        )
        await _edit_payment_message(
            inquiry.telegram_connection_id,
            chat_id,
            message_id,
            payment_detail_text(order, snapshot, locale),
            payment_detail_keyboard(snapshot, token, locale),
        )
        return

    if not payment.destination_snapshot:
        await _answer_payment_callback(callback_query)
        return
    payment.destination_id = None
    payment.destination_snapshot = None
    await session.commit()
    await _answer_payment_callback(callback_query)
    await _refresh_payment_prompt(session, payment, order, inquiry)


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
        business_message = payload.get("business_message") or payload.get("edited_business_message")
        if TELEGRAM_INQUIRIES_ENABLED and isinstance(business_message, dict):
            await _handle_business_message(session, business_message, update_id)
        callback_query = payload.get("callback_query")
        if isinstance(callback_query, dict):
            await _handle_payment_callback(session, callback_query)
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
