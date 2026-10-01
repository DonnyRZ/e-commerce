"""Admin-controlled manual transfer orders and two-leg fulfillment.

This router deliberately does not enable public checkout. It turns a Telegram
cart inquiry into an order only after an authenticated operator supplies the
shipping details, then keeps payment and fulfillment transitions server-side.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import mimetypes
import secrets
import time
import uuid
from datetime import timedelta
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth import csrf_protect, require_roles
from cms.service import audit
from config import (
    APP_ENV,
    ADMIN_TO_CUSTOMER_TRANSIT_DAYS,
    FRONTEND_URL,
    PAYMENT_EVIDENCE_MAX_BYTES,
    PREORDER_ESTIMATE_DAYS,
    SUPPLIER_TO_ADMIN_TRANSIT_DAYS,
    TELEGRAM_BOT_TOKEN,
)
from db.models import (
    ManualPaymentEvidence,
    CmsAuditLog,
    InventoryReservation,
    Order,
    OrderFulfillmentStage,
    OrderItem,
    Payment,
    PaymentDestination,
    PaymentEvent,
    SellerOrderFulfillment,
    TelegramOrderNotificationOutbox,
    TelegramPaymentNotificationOutbox,
    TelegramProductCandidate,
    Product,
    ProductVariant,
    TelegramConversation,
    TelegramCartInquiry,
    User,
    utcnow,
)
from db.session import SessionLocal, get_session
from order_workflow import (
    ACTIONABLE_ORDER_STATUSES,
    WORKFLOW_FILTER_ALIASES,
    WORKFLOW_FILTER_STAGES,
    WORKFLOW_STAGE_STATUS_GROUPS,
    WORKFLOW_STAGES,
    normalize_workflow_filter_stage,
    workflow_stage_for_status,
)
from storage.payment_evidence import delete as delete_evidence_file
from storage.payment_evidence import resolve as resolve_evidence_file
from storage.payment_evidence import save as save_evidence_file
from payment_destinations import (
    MAX_PAYMENT_DESTINATIONS,
    destination_admin_payload,
    mask_account_number,
    normalize_account_number,
    payment_prompt_text,
    payment_choice_keyboard,
)
from telegram_inquiries import TelegramDeliveryError, bot_request
from telegram_inbox_service import (
    active_locale_for_chat,
    normalized_telegram_locale,
    record_outgoing_message,
)

router = APIRouter(prefix="/api/v1", tags=["manual-orders"])
require_admin = require_roles("admin")
logger = logging.getLogger("muslimah_cantik.payment_notifications")
order_notification_logger = logging.getLogger("muslimah_cantik.order_notifications")
PAYMENT_NOTIFICATION_POLL_SECONDS = 1
PAYMENT_NOTIFICATION_STALE_AFTER = timedelta(minutes=2)
ORDER_NOTIFICATION_POLL_SECONDS = 1
ORDER_NOTIFICATION_STALE_AFTER = timedelta(minutes=2)

ORDER_STAGES = {
    "supplier_shipping": {"from": "paid", "to": "supplier_shipping"},
    "received_by_admin": {"from": "supplier_shipping", "to": "received_by_admin"},
    "customer_shipping": {"from": "received_by_admin", "to": "customer_shipping"},
    "delivered": {"from": "customer_shipping", "to": "delivered"},
}
ORDER_NOTIFICATION_LABELS = {
    "supplier_shipping": "Barang dikirim menuju admin",
    "received_by_admin": "Barang diterima admin",
    "customer_shipping": "Barang dikirim ke customer",
    "delivered": "Barang diterima customer",
}
ORDER_NOTIFICATION_COPY = {
    "id": {
        "payment_confirmed": "Pembayaran order {order_number} telah dikonfirmasi. Pesanan sedang diproses.",
        "payment_rejected": "Bukti pembayaran order {order_number} belum dapat diverifikasi. Alasan: {reason}",
        "fulfillment_prefix": "Update order {order_number}: {stage}.",
        "stages": ORDER_NOTIFICATION_LABELS,
    },
    "en": {
        "payment_confirmed": "Payment for order {order_number} has been confirmed. Your order is being processed.",
        "payment_rejected": "We could not verify the payment proof for order {order_number}. Reason: {reason}",
        "fulfillment_prefix": "Order {order_number} update: {stage}.",
        "stages": {
            "supplier_shipping": "The item has been shipped to our team",
            "received_by_admin": "The item has been received by our team",
            "customer_shipping": "The item has been shipped to you",
            "delivered": "The item has been delivered to you",
        },
    },
    "uz": {
        "payment_confirmed": "{order_number} buyurtmasi uchun to‘lov tasdiqlandi. Buyurtmangiz qayta ishlanmoqda.",
        "payment_rejected": "{order_number} buyurtmasi uchun to‘lov chekini tasdiqlay olmadik. Sabab: {reason}",
        "fulfillment_prefix": "{order_number} buyurtma yangilanishi: {stage}.",
        "stages": {
            "supplier_shipping": "Mahsulot admin tomon yuborildi",
            "received_by_admin": "Mahsulot admin tomonidan qabul qilindi",
            "customer_shipping": "Mahsulot sizga yuborildi",
            "delivered": "Mahsulot sizga yetkazildi",
        },
    },
    "ru": {
        "payment_confirmed": "Оплата заказа {order_number} подтверждена. Заказ передан в обработку.",
        "payment_rejected": "Не удалось проверить подтверждение оплаты заказа {order_number}. Причина: {reason}",
        "fulfillment_prefix": "Обновление по заказу {order_number}: {stage}.",
        "stages": {
            "supplier_shipping": "Товар отправлен администратору",
            "received_by_admin": "Товар получен администратором",
            "customer_shipping": "Товар отправлен вам",
            "delivered": "Товар доставлен",
        },
    },
}
ALLOWED_EVIDENCE = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
PUBLIC_ORDER_STAGES = {
    "pending_payment": "pending_payment",
    "payment_review": "payment_review",
    "paid": "paid",
    "supplier_shipping": "supplier_shipping",
    "received_by_admin": "received_by_admin",
    "customer_shipping": "customer_shipping",
    "delivered": "delivered",
    "cancelled": "cancelled",
}


class ManualOrderCreateIn(BaseModel):
    guest_email: Optional[str] = Field(default=None, max_length=255)
    shipping_address: dict[str, Any] = Field(default_factory=dict)
    shipping_method: str = Field(default="manual", min_length=1, max_length=80)
    shipping_amount: int = Field(default=0, ge=0)


class PaymentRejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class PaymentDestinationIn(BaseModel):
    bank_name: str = Field(min_length=2, max_length=100)
    destination_type: Literal["bank_account", "card"]
    account_number: str = Field(min_length=8, max_length=64)
    holder_name: str = Field(min_length=2, max_length=120)
    is_active: bool = True


class PaymentNotificationRetryIn(BaseModel):
    confirm_uncertain: bool = False


class FulfillmentIn(BaseModel):
    stage: str
    carrier: Optional[str] = Field(default=None, max_length=80)
    tracking_number: Optional[str] = Field(default=None, max_length=120)
    shipped_at: Optional[Any] = None
    received_at: Optional[Any] = None
    note: Optional[str] = Field(default=None, max_length=1000)


def _error(status: int, code: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": code, **extra})


def _evidence_content_matches(data: bytes, mime: str) -> bool:
    signatures = {
        "image/jpeg": data[:3] == b"\xff\xd8\xff",
        "image/png": data[:8] == b"\x89PNG\r\n\x1a\n",
        "image/webp": data[:4] == b"RIFF" and data[8:12] == b"WEBP",
        "application/pdf": data[:5] == b"%PDF-",
    }
    return signatures.get(mime, False)


def _order_public_status(order: Order) -> str:
    return PUBLIC_ORDER_STAGES.get(order.status, order.status)


def _workflow_next_action(stage: str) -> str:
    return {
        "inquiry": "review_inquiry",
        "pending_payment": "wait_payment",
        "payment_review": "verify_payment",
        "paid": "supplier_ship",
        "supplier_shipping": "receive_admin",
        "received_by_admin": "ship_customer",
        "customer_shipping": "mark_delivered",
        "delivered": "view_order",
        "processing": "supplier_ship",
        "shipped": "mark_delivered",
    }.get(stage, "view_order")


def _workflow_stage(status: str) -> str:
    """Map a persisted status to its next visible operational checkpoint."""
    return workflow_stage_for_status(status)


def _workflow_filter_stage(stage: str) -> str:
    """Normalize legacy filter URLs without reinterpreting canonical stages."""
    return normalize_workflow_filter_stage(stage)


def _workflow_counts(status_counts: dict[str, int], inquiry_count: int) -> dict[str, int]:
    """Map grouped database counts onto the six visible workflow steps."""
    counts = {key: int(status_counts.get(key, 0)) for key in WORKFLOW_STAGES}
    for key in WORKFLOW_FILTER_STAGES:
        counts.setdefault(key, int(status_counts.get(key, 0)))
    counts["inquiry"] = inquiry_count
    for stage, statuses in WORKFLOW_STAGE_STATUS_GROUPS.items():
        if stage == "inquiry":
            continue
        counts[stage] = sum(int(status_counts.get(status, 0)) for status in statuses)
    return counts


def _workflow_page(entries: list[dict], stage: Optional[str], page: int, page_size: int):
    """Filter and paginate after counts can be calculated over all entries."""
    matching = [entry for entry in entries if stage is None or entry.get("stage") == stage]
    total = len(matching)
    total_pages = max(1, (total + page_size - 1) // page_size)
    effective_page = min(page, total_pages)
    start = (effective_page - 1) * page_size
    return matching[start:start + page_size], total, effective_page


def _customer_name(user: Optional[User], address: dict) -> str:
    recipient = str(address.get("recipient_name") or "").strip()
    if recipient:
        return recipient
    if user:
        name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        if name:
            return name
        if user.email:
            return user.email
    return "Guest Telegram"


def _parse_time(value: Any):
    if value is None:
        return None
    if not isinstance(value, str):
        raise _error(422, "invalid_timestamp")
    try:
        from datetime import datetime

        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _error(422, "invalid_timestamp") from exc


def _order_notification_payload(notification: TelegramOrderNotificationOutbox) -> dict:
    return {
        "event_key": notification.event_key,
        "status": notification.status,
        "error": notification.error_code,
        "message_id": notification.message_id,
        "created_at": notification.created_at,
        "updated_at": notification.updated_at,
    }


def _stage_payload(
    stage: OrderFulfillmentStage,
    notification: Optional[TelegramOrderNotificationOutbox] = None,
) -> dict:
    return {
        "stage": stage.stage,
        "status": stage.status,
        "carrier": stage.carrier,
        "tracking_number": stage.tracking_number,
        "shipped_at": stage.shipped_at,
        "received_at": stage.received_at,
        "expected_at": stage.expected_at,
        "note": stage.note,
        "telegram_notification": (
            _order_notification_payload(notification) if notification else None
        ),
    }


async def _telegram_target_for_order(session: AsyncSession, order_id: str):
    inquiry = await session.scalar(
        select(TelegramCartInquiry).where(TelegramCartInquiry.order_id == order_id)
    )
    if inquiry and inquiry.telegram_connection_id and inquiry.telegram_chat_id:
        locale = await active_locale_for_chat(
            session,
            inquiry.telegram_connection_id,
            inquiry.telegram_chat_id,
            inquiry.locale,
        )
        return inquiry.telegram_connection_id, inquiry.telegram_chat_id, locale
    order = await session.get(Order, order_id)
    if order and order.telegram_conversation_id:
        conversation = await session.get(
            TelegramConversation, order.telegram_conversation_id
        )
        if conversation:
            return (
                conversation.connection_id,
                conversation.chat_id,
                normalized_telegram_locale(conversation.locale),
            )
    return None


async def _queue_order_notification(
    order_id: str,
    event_key: str,
    text: str,
    session: AsyncSession,
    *,
    event_type: str | None = None,
    event_payload: dict | None = None,
) -> TelegramOrderNotificationOutbox:
    """Persist a deduplicated Telegram send in the same transaction as its event."""
    existing = await session.scalar(
        select(TelegramOrderNotificationOutbox).where(
            TelegramOrderNotificationOutbox.order_id == order_id,
            TelegramOrderNotificationOutbox.event_key == event_key,
        )
    )
    if existing:
        return existing
    if event_type is None:
        if event_key == "payment_confirmed":
            event_type = "payment_confirmed"
        elif event_key.startswith("payment_rejected:"):
            event_type = "payment_rejected"
            reason = text.partition("Alasan: ")[2]
            event_payload = {"reason": reason}
        elif event_key.startswith("fulfillment:"):
            event_type = "fulfillment"
            event_payload = {"stage": event_key.partition(":")[2]}
        else:
            event_type = "legacy"
    notification = TelegramOrderNotificationOutbox(
        order_id=order_id,
        event_key=event_key,
        event_type=event_type,
        event_payload=event_payload or {},
        message_text=text[:3900],
        status="pending",
    )
    session.add(notification)
    return notification


def _render_order_notification(notification, order, locale: str) -> str:
    """Render a queued order event with the chat's active locale at send time."""
    event_type = getattr(notification, "event_type", None) or "legacy"
    payload = getattr(notification, "event_payload", None)
    payload = payload if isinstance(payload, dict) else {}
    event_key = str(getattr(notification, "event_key", "") or "")
    message_text = str(getattr(notification, "message_text", "") or "")
    if event_type == "legacy":
        if event_key == "payment_confirmed":
            event_type = "payment_confirmed"
        elif event_key.startswith("payment_rejected:"):
            event_type = "payment_rejected"
            if "reason" not in payload:
                payload = {**payload, "reason": message_text.partition("Alasan: ")[2]}
        elif event_key.startswith("fulfillment:"):
            event_type = "fulfillment"
            payload = {**payload, "stage": event_key.partition(":")[2]}
        else:
            return message_text

    locale = normalized_telegram_locale(locale)
    copy = ORDER_NOTIFICATION_COPY[locale]
    order_number = str(getattr(order, "order_number", "") or "")
    if event_type == "payment_confirmed":
        return copy["payment_confirmed"].format(order_number=order_number)
    if event_type == "payment_rejected":
        reason = str(payload.get("reason") or "")
        return copy["payment_rejected"].format(
            order_number=order_number, reason=reason
        )[:3900]
    if event_type == "fulfillment":
        stage = copy["stages"].get(str(payload.get("stage") or ""))
        if stage:
            return copy["fulfillment_prefix"].format(
                order_number=order_number, stage=stage
            )
    return message_text


async def _recover_stale_order_notifications(session: AsyncSession) -> None:
    """Do not auto-resend a send interrupted after it may have reached Telegram."""
    stale_before = utcnow() - ORDER_NOTIFICATION_STALE_AFTER
    rows = (
        (
            await session.execute(
                select(TelegramOrderNotificationOutbox)
                .where(
                    TelegramOrderNotificationOutbox.status == "sending",
                    or_(
                        TelegramOrderNotificationOutbox.claimed_at.is_(None),
                        TelegramOrderNotificationOutbox.claimed_at <= stale_before,
                    ),
                )
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        row.status = "unknown"
        row.error_code = "delivery_outcome_unknown"
        row.completed_at = utcnow()


async def _dispatch_one_order_notification() -> bool:
    """Send one durable notification without holding up an order API response."""
    async with SessionLocal() as session:
        notification = await session.scalar(
            select(TelegramOrderNotificationOutbox)
            .where(TelegramOrderNotificationOutbox.status == "pending")
            .order_by(TelegramOrderNotificationOutbox.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if not notification:
            return False

        notification.status = "sending"
        notification.claimed_at = utcnow()
        notification.error_code = None
        await session.commit()

        order_id = notification.order_id
        order = await session.get(Order, order_id)
        if not order:
            # The order may have been permanently deleted while this row was
            # being claimed. Its cascading delete is authoritative.
            return True
        target = await _telegram_target_for_order(session, order_id)
        if not target or not TELEGRAM_BOT_TOKEN:
            notification.status = "unavailable"
            notification.error_code = "telegram_chat_unavailable"
            notification.completed_at = utcnow()
            await session.commit()
            return True

        connection_id, chat_id, locale = target
        message_text = _render_order_notification(notification, order, locale)
        try:
            result = await bot_request(
                TELEGRAM_BOT_TOKEN,
                "sendMessage",
                {
                    "business_connection_id": connection_id,
                    "chat_id": chat_id,
                    "text": message_text,
                },
            )
        except TelegramDeliveryError as exc:
            notification.status = "failed"
            notification.error_code = exc.safe_code
            notification.completed_at = utcnow()
            await session.commit()
            return True
        except Exception:
            # Transport failures can happen after Telegram accepted the send;
            # retain an explicit ambiguous state and never resend automatically.
            order_notification_logger.exception(
                "Telegram order notification outcome is unknown"
            )
            notification.status = "unknown"
            notification.error_code = "delivery_outcome_unknown"
            notification.completed_at = utcnow()
            await session.commit()
            return True

        message_id = result.get("message_id") if isinstance(result, dict) else None
        notification.message_id = (
            message_id
            if isinstance(message_id, int) and not isinstance(message_id, bool)
            else None
        )
        notification.status = "sent"
        notification.error_code = None
        notification.completed_at = utcnow()
        await session.commit()
        try:
            await record_outgoing_message(
                session, connection_id, chat_id, result, message_text
            )
        except Exception:
            order_notification_logger.exception(
                "Could not record order notification in Telegram inbox"
            )
        return True


async def order_notification_dispatch_loop() -> None:
    """Recover and dispatch durable order notifications independently of requests."""
    while True:
        try:
            async with SessionLocal() as session:
                await _recover_stale_order_notifications(session)
                await session.commit()
            await _dispatch_one_order_notification()
        except asyncio.CancelledError:
            raise
        except Exception:
            order_notification_logger.exception(
                "Telegram order notification outbox iteration failed"
            )
        await asyncio.sleep(ORDER_NOTIFICATION_POLL_SECONDS)


def _queue_payment_prompt(session: AsyncSession, payment: Payment) -> None:
    """Persist a durable send request without waiting for Telegram's API."""
    payment.telegram_selection_token = secrets.token_urlsafe(12)
    payment.telegram_payment_message_id = None
    payment.telegram_payment_status = "sending"
    payment.telegram_payment_error = None
    session.add(
        TelegramPaymentNotificationOutbox(payment_id=payment.id, status="pending")
    )


async def _recover_stale_payment_notifications(session: AsyncSession) -> None:
    """Mark interrupted requests ambiguous; never resend them automatically."""
    stale_before = utcnow() - PAYMENT_NOTIFICATION_STALE_AFTER
    rows = (
        await session.execute(
            select(TelegramPaymentNotificationOutbox)
            .where(
                TelegramPaymentNotificationOutbox.status == "sending",
                TelegramPaymentNotificationOutbox.claimed_at <= stale_before,
            )
            .with_for_update()
        )
    ).scalars().all()
    for row in rows:
        row.status = "unknown"
        row.error_code = "delivery_outcome_unknown"
        row.completed_at = utcnow()
        payment = await session.get(Payment, row.payment_id)
        if payment and payment.telegram_payment_status == "sending":
            payment.telegram_payment_status = "unknown"
            payment.telegram_payment_error = "delivery_outcome_unknown"


async def _dispatch_one_payment_notification() -> bool:
    """Claim and send one queued prompt. The outbox survives API restarts."""
    async with SessionLocal() as session:
        row = await session.scalar(
            select(TelegramPaymentNotificationOutbox)
            .where(TelegramPaymentNotificationOutbox.status == "pending")
            .order_by(TelegramPaymentNotificationOutbox.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if not row:
            return False
        row.status = "sending"
        row.claimed_at = utcnow()
        await session.commit()

        payment = await session.get(Payment, row.payment_id)
        order = await session.get(Order, payment.order_id) if payment else None
        if not payment or not order:
            row.status = "failed"
            row.error_code = "payment_or_order_missing"
            row.completed_at = utcnow()
            await session.commit()
            return True
        if payment.status != "pending" or order.status != "pending_payment":
            row.status = "failed"
            row.error_code = "payment_notification_locked"
            row.completed_at = utcnow()
            await session.commit()
            return True

        destinations = (
            await session.execute(
                select(PaymentDestination)
                .where(PaymentDestination.is_active.is_(True))
                .order_by(PaymentDestination.slot)
            )
        ).scalars().all()
        if not destinations:
            row.status = "blocked"
            row.error_code = "no_active_destinations"
            row.completed_at = utcnow()
            payment.telegram_payment_status = "blocked"
            payment.telegram_payment_error = "no_active_destinations"
            await session.commit()
            return True

        target = await _telegram_target_for_order(session, order.id)
        if not target or not TELEGRAM_BOT_TOKEN:
            row.status = "unavailable"
            row.error_code = "telegram_chat_unavailable"
            row.completed_at = utcnow()
            payment.telegram_payment_status = "unavailable"
            payment.telegram_payment_error = "telegram_chat_unavailable"
            await session.commit()
            return True

        connection_id, chat_id, locale = target
        token = payment.telegram_selection_token or secrets.token_urlsafe(12)
        payment.telegram_selection_token = token
        count = await session.scalar(
            select(func.coalesce(func.sum(OrderItem.quantity), 0)).where(
                OrderItem.order_id == order.id
            )
        )
        tracking_link = (
            f"{FRONTEND_URL}/orders/track?order_number={order.order_number}&token={order.guest_access_token}"
            if order.guest_access_token
            else f"{FRONTEND_URL}/orders/{order.order_number}"
        )
        message_text = payment_prompt_text(order, int(count or 0), locale, tracking_link)
        await session.commit()

        try:
            result = await bot_request(
                TELEGRAM_BOT_TOKEN,
                "sendMessage",
                {
                    "business_connection_id": connection_id,
                    "chat_id": chat_id,
                    "text": message_text[:3900],
                    "reply_markup": payment_choice_keyboard(destinations, token, locale),
                },
            )
        except TelegramDeliveryError:
            row.status = "failed"
            row.error_code = "telegram_rejected_message"
            row.completed_at = utcnow()
            payment.telegram_payment_status = "failed"
            payment.telegram_payment_error = "telegram_rejected_message"
            await session.commit()
            return True
        except Exception:
            # Timeouts and transport errors can happen after Telegram accepted
            # the message, so the outbox must not retry them automatically.
            logger.exception("Telegram payment prompt delivery outcome is unknown")
            row.status = "unknown"
            row.error_code = "delivery_outcome_unknown"
            row.completed_at = utcnow()
            payment.telegram_payment_status = "unknown"
            payment.telegram_payment_error = "delivery_outcome_unknown"
            await session.commit()
            return True

        message_id = result.get("message_id") if isinstance(result, dict) else None
        payment.telegram_payment_message_id = (
            message_id
            if isinstance(message_id, int) and not isinstance(message_id, bool)
            else None
        )
        payment.telegram_payment_status = "sent"
        payment.telegram_payment_error = None
        row.status = "sent"
        row.error_code = None
        row.completed_at = utcnow()
        await session.commit()
        try:
            await record_outgoing_message(
                session, connection_id, chat_id, result, message_text[:3900]
            )
        except Exception:
            logger.exception("Could not record sent payment prompt in Telegram inbox")
        return True


async def payment_notification_dispatch_loop() -> None:
    """Background dispatcher for durable Telegram payment prompts."""
    while True:
        try:
            async with SessionLocal() as session:
                await _recover_stale_payment_notifications(session)
                await session.commit()
            await _dispatch_one_payment_notification()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Payment notification outbox iteration failed")
        await asyncio.sleep(PAYMENT_NOTIFICATION_POLL_SECONDS)


async def _inquiry_id_for_order(session: AsyncSession, order_id: str) -> Optional[str]:
    return await session.scalar(
        select(TelegramCartInquiry.id).where(TelegramCartInquiry.order_id == order_id)
    )


def _evidence_payload(row: ManualPaymentEvidence) -> dict:
    return {
        "id": row.id,
        "original_filename": row.original_filename,
        "mime_type": row.mime_type,
        "file_size": row.file_size,
        "checksum": row.checksum,
        "created_at": row.created_at,
        "rejection_reason": row.rejection_reason,
        "download_url": f"/api/v1/admin/payment-evidence/{row.id}/download",
    }


async def _load_admin_order(
    order_number: str, session: AsyncSession, *, include_archived: bool = False
) -> Order:
    order = await session.scalar(
        select(Order).where(Order.order_number == order_number).with_for_update()
    )
    if not order:
        raise _error(404, "order_not_found")
    if not include_archived and order.archived_at is not None:
        raise _error(409, "order_archived")
    return order


def _destination_values(payload: PaymentDestinationIn) -> dict[str, Any]:
    bank_name = payload.bank_name.strip()
    holder_name = payload.holder_name.strip()
    if not bank_name or not holder_name:
        raise _error(422, "destination_fields_required")
    try:
        account_number = normalize_account_number(
            payload.account_number, payload.destination_type
        )
    except ValueError as exc:
        raise _error(422, str(exc)) from exc
    return {
        "bank_name": bank_name,
        "destination_type": payload.destination_type,
        "account_number": account_number,
        "holder_name": holder_name,
        "is_active": payload.is_active,
    }


@router.get("/admin/payment-destinations")
async def list_payment_destinations(
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    rows = (
        await session.execute(
            select(PaymentDestination).order_by(PaymentDestination.slot)
        )
    ).scalars().all()
    return {
        "items": [destination_admin_payload(row) for row in rows],
        "active_count": sum(1 for row in rows if row.is_active),
        "max_count": MAX_PAYMENT_DESTINATIONS,
    }


@router.post("/admin/payment-destinations", status_code=201)
async def create_payment_destination(
    payload: PaymentDestinationIn,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    slots = set(
        (await session.scalars(select(PaymentDestination.slot))).all()
    )
    available = next(
        (slot for slot in range(MAX_PAYMENT_DESTINATIONS) if slot not in slots), None
    )
    if available is None:
        raise _error(409, "payment_destination_limit_reached")
    row = PaymentDestination(
        slot=available,
        callback_key=secrets.token_hex(4),
        **_destination_values(payload),
    )
    session.add(row)
    try:
        await session.flush()
        await audit(
            session,
            user.id,
            "admin.payment_destination.create",
            "payment_destination",
            row.id,
            {"bank_name": row.bank_name, "active": row.is_active},
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _error(409, "payment_destination_slot_conflict") from exc
    return destination_admin_payload(row)


@router.get("/admin/payment-destinations/{destination_id}")
async def get_payment_destination(
    destination_id: str,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(PaymentDestination, destination_id)
    if not row:
        raise _error(404, "payment_destination_not_found")
    return destination_admin_payload(row, include_number=True)


@router.patch("/admin/payment-destinations/{destination_id}")
async def update_payment_destination(
    destination_id: str,
    payload: PaymentDestinationIn,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    row = await session.scalar(
        select(PaymentDestination)
        .where(PaymentDestination.id == destination_id)
        .with_for_update()
    )
    if not row:
        raise _error(404, "payment_destination_not_found")
    values = _destination_values(payload)
    changed = any(getattr(row, key) != value for key, value in values.items())
    for key, value in values.items():
        setattr(row, key, value)
    # Previously sent buttons become stale when their destination changes.
    # The callback handler then refreshes the same Telegram message safely.
    if changed:
        row.callback_key = secrets.token_hex(4)
    await audit(
        session,
        user.id,
        "admin.payment_destination.update",
        "payment_destination",
        row.id,
        {"bank_name": row.bank_name, "active": row.is_active},
    )
    await session.commit()
    return destination_admin_payload(row)


@router.get("/admin/telegram-inquiries")
async def list_telegram_inquiries(
    status: Optional[str] = Query(default=None),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    query = select(TelegramCartInquiry).order_by(TelegramCartInquiry.created_at.desc())
    if status:
        query = query.where(TelegramCartInquiry.status == status)
    rows = (await session.execute(query.limit(100))).scalars().all()
    order_ids = [row.order_id for row in rows if row.order_id]
    order_numbers = (
        {
            row.id: row.order_number
            for row in (
                await session.execute(select(Order).where(Order.id.in_(order_ids)))
            )
            .scalars()
            .all()
        }
        if order_ids
        else {}
    )
    return {
        "items": [
            {
                "reference": row.reference,
                "status": row.status,
                "created_at": row.created_at,
                "expires_at": row.expires_at,
                "order_id": row.order_id,
                "order_number": order_numbers.get(row.order_id),
                "user_id": row.user_id,
                "item_count": (
                    (row.snapshot or {}).get("item_count", 0) if row.snapshot else 0
                ),
                "subtotal": (
                    (row.snapshot or {}).get("subtotal", 0) if row.snapshot else 0
                ),
                "currency": (
                    (row.snapshot or {}).get("currency", "UZS")
                    if row.snapshot
                    else "UZS"
                ),
                "snapshot": row.snapshot,
            }
            for row in rows
        ]
    }


@router.get("/admin/telegram-inquiries/{reference}")
async def get_telegram_inquiry(
    reference: str,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    inquiry = await session.scalar(
        select(TelegramCartInquiry).where(TelegramCartInquiry.reference == reference)
    )
    if not inquiry:
        raise _error(404, "inquiry_not_found")
    order_number = None
    if inquiry.order_id:
        order_number = await session.scalar(
            select(Order.order_number).where(Order.id == inquiry.order_id)
        )
    linked_user = await session.get(User, inquiry.user_id) if inquiry.user_id else None
    snapshot = inquiry.snapshot or {}
    items = snapshot.get("items") or []
    return {
        "reference": inquiry.reference,
        "status": inquiry.status,
        "created_at": inquiry.created_at,
        "expires_at": inquiry.expires_at,
        "order_id": inquiry.order_id,
        "order_number": order_number,
        "customer": {
            "name": _customer_name(linked_user, {}),
            "email": linked_user.email if linked_user else None,
        },
        "item_count": len(items),
        "subtotal": snapshot.get("subtotal", 0),
        "currency": snapshot.get("currency", "UZS"),
        "snapshot": snapshot,
    }


@router.delete("/admin/telegram-inquiries/{reference}")
async def permanently_delete_admin_telegram_inquiry(
    reference: str,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    inquiry = await session.scalar(
        select(TelegramCartInquiry)
        .where(TelegramCartInquiry.reference == reference)
        .with_for_update()
    )
    if not inquiry:
        raise _error(404, "inquiry_not_found")
    if inquiry.order_id:
        raise _error(409, "inquiry_already_converted")

    snapshot = inquiry.snapshot if isinstance(inquiry.snapshot, dict) else {}
    delivery = snapshot.get("_delivery") if isinstance(snapshot.get("_delivery"), dict) else {}
    try:
        delivery_age = time.time() - float(delivery.get("started", 0))
    except (TypeError, ValueError):
        delivery_age = float("inf")
    if inquiry.status == "sending" and delivery_age < 300:
        raise _error(409, "inquiry_delivery_in_progress")

    await audit(
        session,
        user.id,
        "admin.telegram_inquiry.permanent_delete",
        "telegram_inquiry",
        inquiry.reference,
        {
            "status": inquiry.status,
            "item_count": len(snapshot.get("items") or []),
            "subtotal": snapshot.get("subtotal"),
            "currency": snapshot.get("currency", "UZS"),
        },
    )
    await session.delete(inquiry)
    await session.commit()
    return {"reference": inquiry.reference, "deleted": True, "scope": "cms"}


@router.get("/admin/order-workflow")
async def list_order_workflow(
    scope: str = Query(default="actionable"),
    stage: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    if scope not in {"all", "actionable"}:
        raise _error(422, "invalid_workflow_scope")
    if stage and stage not in set(WORKFLOW_STAGES) | set(WORKFLOW_FILTER_ALIASES) | {"payment", "archived"}:
        raise _error(422, "invalid_workflow_stage")
    selected_stage = _workflow_filter_stage(stage) if stage else None

    entries: list[dict] = []
    inquiry_query = select(TelegramCartInquiry).where(
        TelegramCartInquiry.order_id.is_(None),
        TelegramCartInquiry.status.in_(["pending", "sending", "sent", "unknown"]),
        TelegramCartInquiry.expires_at > utcnow(),
    )
    if q:
        inquiry_query = inquiry_query.where(
            TelegramCartInquiry.reference.ilike(f"%{q}%")
        )
    inquiries = (
        (await session.execute(inquiry_query.order_by(TelegramCartInquiry.created_at.desc())))
        .scalars()
        .all()
    )
    active_inquiries = []
    for inquiry in inquiries:
        snapshot = inquiry.snapshot or {}
        snapshot_items = snapshot.get("items") or []
        if not snapshot_items:
            continue
        active_inquiries.append((inquiry, snapshot, snapshot_items))
        if selected_stage in {None, "inquiry"}:
            linked_user = await session.get(User, inquiry.user_id) if inquiry.user_id else None
            entries.append(
                {
                    "kind": "inquiry",
                    "reference": inquiry.reference,
                    "stage": "inquiry",
                    "status": inquiry.status,
                    "created_at": inquiry.created_at,
                    "customer": {
                        "name": _customer_name(linked_user, {}),
                        "email": linked_user.email if linked_user else None,
                        "city": None,
                    },
                    "item_count": len(snapshot_items),
                    "subtotal": snapshot.get("subtotal", 0),
                    "grand_total": snapshot.get("subtotal", 0),
                    "currency": snapshot.get("currency", "UZS"),
                    "next_action": _workflow_next_action("inquiry"),
                }
            )

    search_filters = []
    if q:
        like = f"%{q}%"
        search_filters.append(
            or_(
                Order.order_number.ilike(like),
                Order.guest_email.ilike(like),
            )
        )

    archived_count = await session.scalar(
        select(func.count(Order.id)).where(
            *search_filters, Order.archived_at.is_not(None)
        )
    )
    active_order_filters = [*search_filters, Order.archived_at.is_(None)]
    if scope == "actionable":
        active_order_filters.append(Order.status.in_(ACTIONABLE_ORDER_STATUSES))

    grouped_status_rows = (
        await session.execute(
            select(Order.status, func.count(Order.id))
            .where(*active_order_filters)
            .group_by(Order.status)
        )
    ).all()
    status_counts = {status: int(count or 0) for status, count in grouped_status_rows}
    counts = _workflow_counts(status_counts, len(active_inquiries))
    counts["archived"] = int(archived_count or 0)

    archived_filter = (
        Order.archived_at.is_not(None)
        if selected_stage == "archived"
        else Order.archived_at.is_(None)
    )
    order_filters = [*search_filters, archived_filter]
    if scope == "actionable" and selected_stage != "archived":
        order_filters.append(Order.status.in_(ACTIONABLE_ORDER_STATUSES))
    order_query = select(Order).where(*order_filters)
    if selected_stage == "inquiry":
        order_query = order_query.where(Order.id == "__no_order__")
    elif selected_stage and selected_stage != "archived":
        order_query = order_query.where(
            Order.status.in_(WORKFLOW_STAGE_STATUS_GROUPS[selected_stage])
        )
    orders = (
        (await session.execute(order_query.order_by(Order.created_at.desc())))
        .scalars()
        .all()
    )
    order_ids = [order.id for order in orders]
    item_counts = (
        {
            order_id: int(count or 0)
            for order_id, count in (
                await session.execute(
                    select(OrderItem.order_id, func.count(OrderItem.id))
                    .where(OrderItem.order_id.in_(order_ids))
                    .group_by(OrderItem.order_id)
                )
            ).all()
        }
        if order_ids
        else {}
    )
    payments_by_order = (
        {
            payment.order_id: payment
            for payment in (
                await session.execute(
                    select(Payment).where(Payment.order_id.in_(order_ids))
                )
            ).scalars().all()
        }
        if order_ids
        else {}
    )
    evidence_counts = (
        {
            payment_id: int(count or 0)
            for payment_id, count in (
                await session.execute(
                    select(ManualPaymentEvidence.payment_id, func.count(ManualPaymentEvidence.id))
                    .where(
                        ManualPaymentEvidence.payment_id.in_(
                            [payment.id for payment in payments_by_order.values()]
                        )
                    )
                    .group_by(ManualPaymentEvidence.payment_id)
                )
            ).all()
        }
        if payments_by_order
        else {}
    )
    for order in orders:
        items_count = item_counts.get(order.id, 0)
        payment = payments_by_order.get(order.id)
        evidence_count = evidence_counts.get(payment.id, 0) if payment else 0
        address = order.shipping_address or {}
        linked_user = await session.get(User, order.user_id) if order.user_id else None
        normalized_stage = _workflow_stage(order.status)
        next_action = (
            "confirm_payment"
            if order.status in {"pending_payment", "payment_review"} and evidence_count
            else _workflow_next_action(order.status)
        )
        entries.append(
            {
                "kind": "order",
                "order_number": order.order_number,
                "order_source": order.order_source,
                "stage": normalized_stage,
                "status": order.status,
                "archived_at": order.archived_at,
                "payment_state": order.payment_state,
                "created_at": order.created_at,
                "customer": {
                    "name": _customer_name(linked_user, address),
                    "email": order.guest_email or (linked_user.email if linked_user else None),
                    "city": address.get("city"),
                },
                "item_count": int(items_count or 0),
                "subtotal": order.subtotal,
                "grand_total": order.grand_total,
                "currency": order.currency,
                "evidence_count": int(evidence_count or 0),
                "telegram_notification_status": payment.telegram_payment_status if payment else None,
                "next_action": next_action,
            }
        )

    entries.sort(key=lambda item: item["created_at"], reverse=True)
    page_items, total, effective_page = _workflow_page(
        entries, None, page, page_size
    )
    return {
        "items": page_items,
        "counts": counts,
        "total": total,
        "page": effective_page,
        "page_size": page_size,
    }


@router.post("/admin/telegram-inquiries/{reference}/orders", status_code=201)
async def create_manual_order(
    reference: str,
    payload: ManualOrderCreateIn,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    inquiry = await session.scalar(
        select(TelegramCartInquiry)
        .where(TelegramCartInquiry.reference == reference)
        .with_for_update()
    )
    if not inquiry:
        raise _error(404, "inquiry_not_found")
    if inquiry.order_id:
        order = await session.get(Order, inquiry.order_id)
        if order:
            return await _admin_order_payload(session, order)
    if inquiry.status == "expired" or inquiry.expires_at <= utcnow():
        raise _error(409, "inquiry_expired")
    if not inquiry.telegram_chat_id or not inquiry.telegram_connection_id or inquiry.status not in ("sent", "unknown"):
        raise _error(409, "inquiry_not_received")
    snapshot = inquiry.snapshot or {}
    snapshot_items = snapshot.get("items") or []
    if not snapshot_items:
        raise _error(409, "inquiry_snapshot_missing")
    if not payload.shipping_address.get(
        "recipient_name"
    ) or not payload.shipping_address.get("phone"):
        raise _error(422, "shipping_recipient_required")
    if idempotency_key:
        existing = await session.scalar(
            select(Order).where(Order.idempotency_key == idempotency_key)
        )
        if existing:
            existing_inquiry_id = await _inquiry_id_for_order(session, existing.id)
            if existing_inquiry_id != inquiry.id:
                raise _error(409, "idempotency_key_conflict")
            return await _admin_order_payload(session, existing)

    skus = [str(item.get("sku") or "") for item in snapshot_items]
    if any(not sku for sku in skus) or len(set(skus)) != len(skus):
        raise _error(409, "inquiry_item_invalid")
    variants = {
        row.sku: row
        for row in (
            await session.execute(
                select(ProductVariant).where(ProductVariant.sku.in_(skus))
            )
        )
        .scalars()
        .all()
    }
    if len(variants) != len(skus):
        raise _error(409, "catalog_item_missing")

    subtotal = 0
    order_lines = []
    for raw in snapshot_items:
        quantity = raw.get("quantity")
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
            raise _error(409, "invalid_quantity")
        variant = variants[str(raw["sku"])]
        product = await session.get(Product, variant.product_id)
        if not product or not variant.is_active or product.status != "active":
            raise _error(409, "catalog_item_unavailable", sku=variant.sku)
        unit_price = (
            variant.sale_price_override
            if variant.sale_price_override is not None
            else (
                variant.price_override
                if variant.price_override is not None
                else product.base_price
            )
        )
        line_total = int(unit_price) * quantity
        subtotal += line_total
        order_lines.append((raw, product, variant, unit_price, line_total, quantity))

    order_number = f"MC-{uuid.uuid4().hex[:10].upper()}"
    linked_user = await session.get(User, inquiry.user_id) if inquiry.user_id else None
    order = Order(
        order_number=order_number,
        user_id=inquiry.user_id,
        guest_email=payload.guest_email or (linked_user.email if linked_user else None),
        guest_access_token=None if inquiry.user_id else secrets.token_urlsafe(24),
        shipping_address=payload.shipping_address,
        shipping_method=payload.shipping_method,
        subtotal=subtotal,
        shipping_amount=payload.shipping_amount,
        grand_total=subtotal + payload.shipping_amount,
        currency=snapshot.get("currency") or "UZS",
        payment_state="unpaid",
        status="pending_payment",
        idempotency_key=idempotency_key,
        order_source="telegram_manual",
        fulfillment_mode="pre_order",
        preorder_estimate_days=PREORDER_ESTIMATE_DAYS,
    )
    session.add(order)
    await session.flush()
    for raw, product, variant, unit_price, line_total, quantity in order_lines:
        session.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                variant_id=variant.id,
                seller_id=product.seller_id,
                sku=variant.sku,
                product_name=str(raw.get("name") or product.slug)[:255],
                option_values=variant.option_values or {},
                image_url=raw.get("image_url"),
                unit_price=unit_price,
                quantity=quantity,
                line_total=line_total,
            )
        )
    payment = Payment(
        order_id=order.id,
        provider="manual_transfer",
        environment=APP_ENV,
        currency=order.currency,
        amount=order.grand_total,
        status="pending",
        merchant_trans_id=f"MANUAL-{uuid.uuid4().hex[:20].upper()}",
    )
    session.add(payment)
    await session.flush()
    _queue_payment_prompt(session, payment)
    inquiry.order_id = order.id
    inquiry.status = "order_created"
    # The order items now contain the immutable commercial snapshot. Remove
    # the temporary Telegram copy after conversion for retention/privacy.
    inquiry.snapshot = None
    await audit(
        session,
        user.id,
        "admin.manual_order.create",
        "order",
        order.order_number,
        {"inquiry": reference},
    )
    await session.commit()
    return await _admin_order_payload(session, order)


@router.post("/admin/orders/{order_number}/payment-notification")
async def retry_payment_notification(
    order_number: str,
    payload: PaymentNotificationRetryIn,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    order = await _load_admin_order(order_number, session)
    payment = await session.scalar(
        select(Payment).where(Payment.order_id == order.id).with_for_update()
    )
    if not payment:
        raise _error(409, "payment_record_missing")
    if order.status != "pending_payment" or payment.status != "pending":
        raise _error(409, "payment_notification_locked")
    if payment.destination_snapshot:
        raise _error(409, "payment_destination_already_selected")
    latest_attempt = await session.scalar(
        select(TelegramPaymentNotificationOutbox)
        .where(TelegramPaymentNotificationOutbox.payment_id == payment.id)
        .order_by(TelegramPaymentNotificationOutbox.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    if payment.telegram_payment_status == "sending":
        sending_is_stale = bool(
            (
                latest_attempt
                and latest_attempt.status == "sending"
                and latest_attempt.claimed_at
                and latest_attempt.claimed_at <= utcnow() - PAYMENT_NOTIFICATION_STALE_AFTER
            )
            or (
                latest_attempt is None
                and payment.updated_at
                and payment.updated_at <= utcnow() - PAYMENT_NOTIFICATION_STALE_AFTER
            )
        )
        if not sending_is_stale:
            raise _error(409, "payment_notification_in_progress")
        if not payload.confirm_uncertain:
            raise _error(409, "payment_notification_outcome_uncertain")
        if latest_attempt:
            latest_attempt.status = "unknown"
            latest_attempt.error_code = "delivery_outcome_unknown"
            latest_attempt.completed_at = utcnow()
        payment.telegram_payment_status = "unknown"
        payment.telegram_payment_error = "delivery_outcome_unknown"
    if payment.telegram_payment_status == "sent":
        raise _error(409, "payment_notification_already_sent")
    if (
        payment.telegram_payment_status == "unknown"
        and not payload.confirm_uncertain
    ):
        raise _error(409, "payment_notification_outcome_uncertain")
    if payment.telegram_payment_status not in {
        "not_sent",
        "blocked",
        "unavailable",
        "failed",
        "unknown",
        "sending",
    }:
        raise _error(409, "payment_notification_not_retryable")
    previous_status = payment.telegram_payment_status
    _queue_payment_prompt(session, payment)
    await audit(
        session,
        user.id,
        "admin.payment_notification.retry",
        "order",
        order.order_number,
        {"previous_status": previous_status},
    )
    await session.commit()
    return await _admin_order_payload(session, order)


@router.post("/admin/orders/{order_number}/payment-evidence", status_code=201)
async def upload_payment_evidence(
    order_number: str,
    file: UploadFile = File(...),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    order = await _load_admin_order(order_number, session)
    payment = await session.scalar(
        select(Payment).where(Payment.order_id == order.id).with_for_update()
    )
    if not payment:
        raise _error(409, "payment_record_missing")
    if order.status in {"delivered", "cancelled"} or payment.status == "paid":
        raise _error(409, "payment_locked")
    mime = (file.content_type or "").lower()
    if mime not in ALLOWED_EVIDENCE:
        raise _error(415, "unsupported_payment_evidence_type")
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await file.read(min(64 * 1024, PAYMENT_EVIDENCE_MAX_BYTES + 1 - size))
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
        if size > PAYMENT_EVIDENCE_MAX_BYTES:
            raise _error(
                413, "payment_evidence_too_large", max_bytes=PAYMENT_EVIDENCE_MAX_BYTES
            )
    data = b"".join(chunks)
    if not data:
        raise _error(400, "empty_payment_evidence")
    if not _evidence_content_matches(data, mime):
        raise _error(415, "payment_evidence_content_mismatch")
    checksum = hashlib.sha256(data).hexdigest()
    key = f"{uuid.uuid4().hex}{mimetypes.guess_extension(mime) or '.bin'}"
    save_evidence_file(data, key)
    evidence = ManualPaymentEvidence(
        payment_id=payment.id,
        storage_key=key,
        original_filename=(file.filename or "evidence")[:255],
        mime_type=mime,
        file_size=size,
        checksum=checksum,
        uploaded_by=user.id,
    )
    session.add(evidence)
    # New orders stay in the single payment stage until an admin has checked
    # the bank statement and explicitly confirmed receipt. Preserve the old
    # review status for already-existing orders during the UX transition.
    if order.status == "payment_review":
        payment.status = "pending_review"
        payment.failure_code = None
        payment.failure_note = None
        payment.review_note = None
    await audit(
        session,
        user.id,
        "admin.payment.evidence.upload",
        "payment",
        payment.id,
        {"size": size},
    )
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        delete_evidence_file(key)
        raise
    return _evidence_payload(evidence)


@router.get("/admin/orders/{order_number}/payment-evidence")
async def list_payment_evidence(
    order_number: str,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    order = await session.scalar(
        select(Order).where(Order.order_number == order_number)
    )
    if not order:
        raise _error(404, "order_not_found")
    payment = await session.scalar(select(Payment).where(Payment.order_id == order.id))
    if not payment:
        return {"items": []}
    rows = (
        (
            await session.execute(
                select(ManualPaymentEvidence)
                .where(ManualPaymentEvidence.payment_id == payment.id)
                .order_by(ManualPaymentEvidence.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return {"items": [_evidence_payload(row) for row in rows]}


@router.get("/admin/payment-evidence/{evidence_id}/download")
async def download_payment_evidence(
    evidence_id: str,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    evidence = await session.get(ManualPaymentEvidence, evidence_id)
    if not evidence:
        raise _error(404, "payment_evidence_not_found")
    path = resolve_evidence_file(evidence.storage_key)
    if not path.exists():
        raise _error(404, "payment_evidence_file_missing")
    return FileResponse(
        path, media_type=evidence.mime_type, filename=evidence.original_filename
    )


@router.post("/admin/orders/{order_number}/payment/confirm")
async def confirm_manual_payment(
    order_number: str,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    order = await _load_admin_order(order_number, session)
    payment = await session.scalar(
        select(Payment).where(Payment.order_id == order.id).with_for_update()
    )
    if not payment:
        raise _error(409, "payment_record_missing")
    if payment.status == "paid":
        return await _admin_order_payload(session, order)
    if payment.status not in {"pending", "pending_review"} or order.status not in {
        "pending_payment",
        "payment_review",
    }:
        raise _error(409, "payment_not_eligible")
    evidence_id = await session.scalar(
        select(ManualPaymentEvidence.id)
        .where(ManualPaymentEvidence.payment_id == payment.id)
        .order_by(ManualPaymentEvidence.created_at.desc())
        .limit(1)
    )
    if not evidence_id:
        raise _error(409, "payment_evidence_required")
    now = utcnow()
    payment.status = "paid"
    payment.paid_at = now
    payment.reviewed_by = user.id
    payment.reviewed_at = now
    payment.review_note = "Manual transfer verified by admin; pre-order procurement started"
    order.payment_state = "paid"
    order.status = "paid"
    await _queue_order_notification(
        order.id,
        "payment_confirmed",
        f"Pembayaran order {order.order_number} telah dikonfirmasi. Pesanan sedang diproses.",
        session,
        event_type="payment_confirmed",
    )
    await audit(
        session,
        user.id,
        "admin.payment.confirm",
        "payment",
        payment.id,
        {"order": order.order_number},
    )
    await session.commit()
    return await _admin_order_payload(session, order)


@router.post("/admin/orders/{order_number}/payment/reject")
async def reject_manual_payment(
    order_number: str,
    payload: PaymentRejectIn,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    order = await _load_admin_order(order_number, session)
    payment = await session.scalar(
        select(Payment).where(Payment.order_id == order.id).with_for_update()
    )
    if not payment or payment.status == "paid":
        raise _error(409, "payment_locked")
    latest = await session.scalar(
        select(ManualPaymentEvidence)
        .where(ManualPaymentEvidence.payment_id == payment.id)
        .order_by(ManualPaymentEvidence.created_at.desc())
    )
    if not latest:
        raise _error(409, "payment_evidence_required")
    latest.rejection_reason = payload.reason
    payment.status = "rejected"
    payment.failure_code = "manual_review_rejected"
    payment.failure_note = payload.reason
    payment.review_note = payload.reason
    payment.reviewed_by = user.id
    payment.reviewed_at = utcnow()
    order.payment_state = "review"
    order.status = "payment_review"
    reason_digest = hashlib.sha256(payload.reason.strip().encode("utf-8")).hexdigest()[
        :16
    ]
    await _queue_order_notification(
        order.id,
        f"payment_rejected:{latest.id}:{reason_digest}",
        f"Bukti pembayaran order {order.order_number} belum dapat diverifikasi. Alasan: {payload.reason}",
        session,
        event_type="payment_rejected",
        event_payload={"reason": payload.reason},
    )
    await audit(
        session,
        user.id,
        "admin.payment.reject",
        "payment",
        payment.id,
        {"reason": payload.reason},
    )
    await session.commit()
    return await _admin_order_payload(session, order)


@router.post("/admin/orders/{order_number}/fulfillment")
async def update_manual_fulfillment(
    order_number: str,
    payload: FulfillmentIn,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    if payload.stage not in ORDER_STAGES:
        raise _error(422, "invalid_fulfillment_stage")
    order = await _load_admin_order(order_number, session)
    transition = ORDER_STAGES[payload.stage]
    if order.payment_state != "paid":
        raise _error(409, "payment_not_eligible")
    if order.status != transition["from"]:
        raise _error(
            409,
            "invalid_fulfillment_transition",
            current=order.status,
            expected=transition["from"],
        )
    stage = await session.scalar(
        select(OrderFulfillmentStage)
        .where(
            OrderFulfillmentStage.order_id == order.id,
            OrderFulfillmentStage.stage == payload.stage,
        )
        .with_for_update()
    )
    if stage and stage.status == "completed":
        raise _error(409, "stage_already_completed")
    if stage is None:
        stage = OrderFulfillmentStage(order_id=order.id, stage=payload.stage)
        session.add(stage)
    now = utcnow()
    stage.status = "completed"
    stage.carrier = payload.carrier
    stage.tracking_number = payload.tracking_number
    stage.note = payload.note
    stage.acted_by = user.id
    if payload.stage in {"supplier_shipping", "customer_shipping"}:
        stage.shipped_at = _parse_time(payload.shipped_at) or now
    else:
        stage.received_at = _parse_time(payload.received_at) or now
    if payload.stage == "supplier_shipping":
        stage.expected_at = stage.shipped_at + timedelta(
            days=SUPPLIER_TO_ADMIN_TRANSIT_DAYS
        )
    elif payload.stage == "customer_shipping":
        stage.expected_at = stage.shipped_at + timedelta(
            days=ADMIN_TO_CUSTOMER_TRANSIT_DAYS
        )
    order.status = transition["to"]
    await _queue_order_notification(
        order.id,
        f"fulfillment:{payload.stage}",
        f"Update order {order.order_number}: {ORDER_NOTIFICATION_LABELS[payload.stage]}.",
        session,
        event_type="fulfillment",
        event_payload={"stage": payload.stage},
    )
    await audit(
        session,
        user.id,
        "admin.order.fulfillment",
        "order",
        order.order_number,
        {"stage": payload.stage, "tracking": payload.tracking_number},
    )
    await session.commit()
    return await _admin_order_payload(session, order)


async def _admin_order_payload(session: AsyncSession, order: Order) -> dict:
    items = (
        (
            await session.execute(
                select(OrderItem)
                .where(OrderItem.order_id == order.id)
                .order_by(OrderItem.id)
            )
        )
        .scalars()
        .all()
    )
    payment = await session.scalar(select(Payment).where(Payment.order_id == order.id))
    evidence = []
    if payment:
        evidence = (
            (
                await session.execute(
                    select(ManualPaymentEvidence)
                    .where(ManualPaymentEvidence.payment_id == payment.id)
                    .order_by(ManualPaymentEvidence.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
    stages = (
        (
            await session.execute(
                select(OrderFulfillmentStage)
                .where(OrderFulfillmentStage.order_id == order.id)
                .order_by(OrderFulfillmentStage.created_at)
            )
        )
        .scalars()
        .all()
    )
    telegram_notifications = (
        (
            await session.execute(
                select(TelegramOrderNotificationOutbox)
                .where(TelegramOrderNotificationOutbox.order_id == order.id)
                .order_by(TelegramOrderNotificationOutbox.created_at.desc())
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    notifications_by_event = {row.event_key: row for row in telegram_notifications}
    activity_target_ids = [order.order_number]
    if payment:
        activity_target_ids.append(payment.id)
    activity = (
        (
            await session.execute(
                select(CmsAuditLog)
                .where(CmsAuditLog.target_id.in_(activity_target_ids))
                .order_by(CmsAuditLog.created_at.desc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    return {
        "order_number": order.order_number,
        "created_at": order.created_at,
        "status": order.status,
        "archived_at": order.archived_at,
        "payment_state": order.payment_state,
        "order_source": order.order_source,
        "fulfillment_mode": order.fulfillment_mode,
        "preorder_estimate_days": order.preorder_estimate_days,
        "grand_total": order.grand_total,
        "currency": order.currency,
        "subtotal": order.subtotal,
        "shipping_amount": order.shipping_amount,
        "shipping_method": order.shipping_method,
        "email": order.guest_email,
        "user_id": order.user_id,
        "shipping_address": order.shipping_address or {},
        "items": [
            {
                "product_name": i.product_name,
                "sku": i.sku,
                "option_values": i.option_values or {},
                "image_url": i.image_url,
                "unit_price": i.unit_price,
                "quantity": i.quantity,
                "line_total": i.line_total,
            }
            for i in items
        ],
        "payment": (
            {
                "id": payment.id,
                "provider": payment.provider,
                "status": payment.status,
                "amount": payment.amount,
                "merchant_trans_id": payment.merchant_trans_id,
                "paid_at": payment.paid_at,
                "failure_note": payment.failure_note,
                "review_note": payment.review_note,
                "telegram_notification": {
                    "status": payment.telegram_payment_status,
                    "error": payment.telegram_payment_error,
                    "message_id": payment.telegram_payment_message_id,
                    "updated_at": payment.updated_at,
                },
                "destination": (
                    {
                        "bank_name": payment.destination_snapshot.get("bank_name"),
                        "destination_type": payment.destination_snapshot.get(
                            "destination_type"
                        ),
                        "masked_account_number": mask_account_number(
                            payment.destination_snapshot.get("account_number")
                        ),
                        "holder_name": payment.destination_snapshot.get("holder_name"),
                    }
                    if payment.destination_snapshot
                    else None
                ),
                "evidence": [_evidence_payload(item) for item in evidence],
            }
            if payment
            else None
        ),
        "fulfillment": [
            _stage_payload(
                stage,
                notifications_by_event.get(f"fulfillment:{stage.stage}"),
            )
            for stage in stages
        ],
        "telegram_notifications": [
            _order_notification_payload(notification)
            for notification in telegram_notifications
        ],
        "activity": [
            {
                "action": row.action,
                "target_type": row.target_type,
                "created_at": row.created_at,
                "metadata": row.safe_metadata or {},
            }
            for row in activity
        ],
    }


@router.get("/admin/orders/{order_number}")
async def get_manual_order_detail(
    order_number: str,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    order = await session.scalar(
        select(Order).where(Order.order_number == order_number)
    )
    if not order:
        raise _error(404, "order_not_found")
    return await _admin_order_payload(session, order)


@router.post("/admin/orders/{order_number}/archive")
async def archive_admin_order(
    order_number: str,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    order = await _load_admin_order(order_number, session, include_archived=True)
    if order.archived_at is None:
        order.archived_at = utcnow()
        await audit(
            session,
            user.id,
            "admin.order.archive",
            "order",
            order.order_number,
            {"status": order.status, "payment_state": order.payment_state},
        )
        await session.commit()
    return {
        "order_number": order.order_number,
        "archived": True,
        "archived_at": order.archived_at,
    }


@router.post("/admin/orders/{order_number}/restore")
async def restore_admin_order(
    order_number: str,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    order = await _load_admin_order(order_number, session, include_archived=True)
    if order.archived_at is not None:
        order.archived_at = None
        await audit(
            session,
            user.id,
            "admin.order.restore",
            "order",
            order.order_number,
            {"status": order.status, "payment_state": order.payment_state},
        )
        await session.commit()
    return {"order_number": order.order_number, "archived": False}


@router.delete("/admin/orders/{order_number}")
async def permanently_delete_admin_order(
    order_number: str,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    order = await _load_admin_order(order_number, session, include_archived=True)
    payments = (
        (
            await session.execute(
                select(Payment).where(Payment.order_id == order.id)
            )
        )
        .scalars()
        .all()
    )
    payment_ids = [payment.id for payment in payments]
    evidence = []
    if payment_ids:
        payment_notifications = (
            (
                await session.execute(
                    select(TelegramPaymentNotificationOutbox)
                    .where(TelegramPaymentNotificationOutbox.payment_id.in_(payment_ids))
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        if any(row.status == "sending" for row in payment_notifications):
            raise _error(409, "payment_notification_in_progress")
        evidence = (
            (
                await session.execute(
                    select(ManualPaymentEvidence).where(
                        ManualPaymentEvidence.payment_id.in_(payment_ids)
                    )
                )
            )
            .scalars()
            .all()
        )

    order_notifications = (
        (
            await session.execute(
                select(TelegramOrderNotificationOutbox)
                .where(TelegramOrderNotificationOutbox.order_id == order.id)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    if any(row.status == "sending" for row in order_notifications):
        raise _error(409, "order_notification_in_progress")

    evidence_storage_keys = [item.storage_key for item in evidence]
    await audit(
        session,
        user.id,
        "admin.order.permanent_delete",
        "order",
        order.order_number,
        {
            "status": order.status,
            "payment_state": order.payment_state,
            "grand_total": order.grand_total,
            "currency": order.currency,
            "payment_count": len(payments),
            "evidence_count": len(evidence),
        },
    )

    # Keep chat transcripts and their confirmed-candidate history, but detach
    # links to the order so they cannot point at a permanently deleted record.
    await session.execute(
        update(TelegramCartInquiry)
        .where(TelegramCartInquiry.order_id == order.id)
        .values(order_id=None, status="order_deleted")
    )
    await session.execute(
        update(TelegramProductCandidate)
        .where(TelegramProductCandidate.order_id == order.id)
        .values(order_id=None, status="order_deleted")
    )

    if payment_ids:
        await session.execute(
            delete(ManualPaymentEvidence).where(
                ManualPaymentEvidence.payment_id.in_(payment_ids)
            )
        )
        await session.execute(
            delete(PaymentEvent).where(PaymentEvent.payment_id.in_(payment_ids))
        )
        await session.execute(
            delete(TelegramPaymentNotificationOutbox).where(
                TelegramPaymentNotificationOutbox.payment_id.in_(payment_ids)
            )
        )
        await session.execute(delete(Payment).where(Payment.id.in_(payment_ids)))

    await session.execute(delete(OrderItem).where(OrderItem.order_id == order.id))
    await session.execute(
        delete(OrderFulfillmentStage).where(OrderFulfillmentStage.order_id == order.id)
    )
    await session.execute(
        delete(TelegramOrderNotificationOutbox).where(
            TelegramOrderNotificationOutbox.order_id == order.id
        )
    )
    reservation_ids = (
        (
            await session.execute(
                select(InventoryReservation.id).where(
                    InventoryReservation.order_id == order.id
                )
            )
        )
        .scalars()
        .all()
    )
    if reservation_ids:
        await session.execute(
            update(InventoryReservation)
            .where(InventoryReservation.reacquired_from.in_(reservation_ids))
            .values(reacquired_from=None)
        )
        await session.execute(
            delete(InventoryReservation).where(
                InventoryReservation.id.in_(reservation_ids)
            )
        )
    await session.execute(
        delete(SellerOrderFulfillment).where(
            SellerOrderFulfillment.order_id == order.id
        )
    )
    await session.execute(delete(Order).where(Order.id == order.id))
    await session.commit()

    for storage_key in evidence_storage_keys:
        try:
            delete_evidence_file(storage_key)
        except Exception:
            logger.exception(
                "Could not remove payment evidence after permanent order deletion"
            )

    return {"order_number": order_number, "deleted": True}
