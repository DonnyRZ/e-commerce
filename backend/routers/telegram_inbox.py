"""Admin API for Telegram Business chat and chat-originated orders."""

from __future__ import annotations

import base64
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import String, and_, case, cast, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth import csrf_protect, require_roles
from cms.service import audit
from config import FRONTEND_URL, TELEGRAM_BOT_TOKEN
from db.models import (
    Category,
    Order,
    Product,
    ProductTranslation,
    ProductVariant,
    TelegramBusinessConnection,
    TelegramCartInquiry,
    TelegramConversation,
    TelegramInboxMessage,
    TelegramProductCandidate,
    User,
    utcnow,
)
from db.session import get_session
from telegram_inbox_service import (
    apply_direct_default_locale,
    candidate_copy,
    candidate_keyboard,
)
from telegram_inquiries import (
    TelegramDeliveryError,
    bot_request,
    bot_request_multipart,
    snapshot_rich_content,
)
from order_workflow import (
    WORKFLOW_FILTER_STAGES,
    TERMINAL_ORDER_STATUSES,
    normalize_workflow_filter_stage,
    telegram_conversation_stage,
    telegram_conversation_stage_sql,
    workflow_stage_for_status,
    workflow_stage_sql,
)

router = APIRouter(prefix="/api/v1/admin/telegram-inbox", tags=["telegram-inbox"])
INQUIRY_REFERENCE_RE = re.compile(r"\bSC-[A-F0-9]{32}\b", re.IGNORECASE)
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


class InboxPendingOrderCreateIn(BaseModel):
    candidate_ids: list[str] = Field(min_length=1, max_length=50)


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
    is_deleted = row.deleted_at is not None
    stored_rich = row.rich_content if isinstance(row.rich_content, dict) else None
    rich_content = None
    if stored_rich and not is_deleted:
        slides = []
        stored_slides = stored_rich.get("slides")
        for index, slide in enumerate(stored_slides if isinstance(stored_slides, list) else []):
            if not isinstance(slide, dict):
                continue
            photo_file_id = slide.get("photo_file_id")
            image_url = slide.get("image_url")
            if photo_file_id:
                image_url = f"/api/v1/admin/telegram-inbox/media/{row.id}?media_index={index}"
            slides.append({
                "caption": str(slide.get("caption") or ""),
                "image_url": image_url if isinstance(image_url, str) else None,
            })
        rich_content = {
            "title": str(stored_rich.get("title") or ""),
            "intro": str(stored_rich.get("intro") or ""),
            "slides": slides,
            "footer": [
                value
                for value in (
                    stored_rich.get("footer")
                    if isinstance(stored_rich.get("footer"), list)
                    else []
                )
                if isinstance(value, str)
            ],
        }
    return {
        "id": row.id,
        "telegram_message_id": row.telegram_message_id,
        "direction": row.direction,
        "source": row.source,
        "type": row.message_type,
        "text": row.text,
        "rich_content": rich_content,
        "media_group_id": row.media_group_id if not is_deleted else None,
        "photo_url": (
            f"/api/v1/admin/telegram-inbox/media/{row.id}"
            if row.photo_file_id and not is_deleted
            else None
        ),
        "is_deleted": is_deleted,
        "created_at": row.created_at,
        "edited_at": row.edited_at,
    }


def _reconstructed_cart_message(inquiry: TelegramCartInquiry) -> dict:
    return {
        "id": f"reconstructed-{inquiry.id}",
        "telegram_message_id": None,
        "direction": "outbound",
        "source": "snapshot",
        "type": "rich",
        "text": "",
        "rich_content": snapshot_rich_content(inquiry.snapshot or {}, inquiry.reference),
        "media_group_id": None,
        "photo_url": None,
        "is_deleted": False,
        "is_reconstructed": True,
        "created_at": inquiry.delivered_at,
        "edited_at": None,
    }


def _order_summary(order: Optional[Order]) -> Optional[dict]:
    if not order:
        return None
    return {
        "order_number": order.order_number,
        "status": order.status,
        "stage": workflow_stage_for_status(order.status, "inquiry"),
        "archived_at": order.archived_at,
        "created_at": order.created_at,
    }


async def _conversation_order_context(session: AsyncSession, row: TelegramConversation):
    orders = (
        await session.execute(
            select(Order)
            .where(Order.telegram_conversation_id == row.id)
            .order_by(Order.created_at.desc(), Order.id.desc())
        )
    ).scalars().all()
    active_orders = [
        order for order in orders
        if order.archived_at is None and order.status not in TERMINAL_ORDER_STATUSES
    ]
    non_archived_orders = [order for order in orders if order.archived_at is None]
    chosen_order = (
        active_orders[0]
        if active_orders
        else non_archived_orders[0]
        if non_archived_orders
        else orders[0]
        if orders
        else None
    )
    non_delivered_orders = [order for order in non_archived_orders if order.status != "delivered"]
    workflow_stage = telegram_conversation_stage(
        conversation_status=row.status,
        total_orders=len(orders),
        non_archived_orders=len(non_archived_orders),
        active_orders=len(active_orders),
        non_delivered_orders=len(non_delivered_orders),
        selected_order_status=active_orders[0].status if active_orders else None,
    )
    return workflow_stage, len(orders), _order_summary(chosen_order), orders


def _conversation_payload(
    row: TelegramConversation,
    last_message: Optional[TelegramInboxMessage],
    *,
    workflow_stage: str = "inquiry",
    order_count: int = 0,
    latest_order: Optional[dict] = None,
) -> dict:
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
        "workflow_stage": workflow_stage,
        "order_count": order_count,
        "latest_order": latest_order,
    }


def _cursor_encode(row: TelegramConversation) -> str:
    raw = json.dumps(
        {"at": row.last_message_at.isoformat(), "id": row.id},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _cursor_decode(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        value = json.loads(raw.decode("utf-8"))
        timestamp = datetime.fromisoformat(value["at"])
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        conversation_id = value["id"]
        if not isinstance(conversation_id, str) or not conversation_id:
            raise ValueError("missing conversation id")
        return timestamp, conversation_id
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error(422, "invalid_inbox_cursor") from exc


def _conversation_stage_cte():
    priority = case(
        (
            and_(
                Order.archived_at.is_(None),
                Order.status.not_in(TERMINAL_ORDER_STATUSES),
            ),
            0,
        ),
        (Order.archived_at.is_(None), 1),
        else_=2,
    )
    ranked_orders = (
        select(
            Order.telegram_conversation_id.label("conversation_id"),
            Order.id.label("order_id"),
            Order.order_number.label("order_number"),
            Order.status.label("status"),
            Order.archived_at.label("archived_at"),
            Order.created_at.label("created_at"),
            workflow_stage_sql(Order.status, "inquiry").label("workflow_stage"),
            func.row_number().over(
                partition_by=Order.telegram_conversation_id,
                order_by=(priority.asc(), Order.created_at.desc(), Order.id.desc()),
            ).label("order_rank"),
        )
        .where(Order.telegram_conversation_id.is_not(None))
        .cte("telegram_inbox_ranked_orders")
    )
    order_stats = (
        select(
            Order.telegram_conversation_id.label("conversation_id"),
            func.count(Order.id).label("total_orders"),
            func.sum(case((Order.archived_at.is_(None), 1), else_=0)).label("non_archived_orders"),
            func.sum(
                case(
                    (
                        and_(
                            Order.archived_at.is_(None),
                            Order.status.not_in(TERMINAL_ORDER_STATUSES),
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("active_orders"),
            func.sum(
                case(
                    (
                        and_(Order.archived_at.is_(None), Order.status != "delivered"),
                        1,
                    ),
                    else_=0,
                )
            ).label("non_delivered_orders"),
        )
        .where(Order.telegram_conversation_id.is_not(None))
        .group_by(Order.telegram_conversation_id)
        .cte("telegram_inbox_order_stats")
    )
    chosen_order = (
        select(ranked_orders)
        .where(ranked_orders.c.order_rank == 1)
        .cte("telegram_inbox_chosen_order")
    )
    total_orders = func.coalesce(order_stats.c.total_orders, 0)
    non_archived_orders = func.coalesce(order_stats.c.non_archived_orders, 0)
    active_orders = func.coalesce(order_stats.c.active_orders, 0)
    non_delivered_orders = func.coalesce(order_stats.c.non_delivered_orders, 0)
    resolved_stage = telegram_conversation_stage_sql(
        TelegramConversation.status,
        total_orders,
        non_archived_orders,
        active_orders,
        non_delivered_orders,
        chosen_order.c.status,
    )
    return (
        select(
            TelegramConversation.id.label("conversation_id"),
            resolved_stage.label("workflow_stage"),
            total_orders.label("order_count"),
            chosen_order.c.order_number.label("latest_order_number"),
            chosen_order.c.status.label("latest_order_status"),
            chosen_order.c.archived_at.label("latest_order_archived_at"),
            chosen_order.c.created_at.label("latest_order_created_at"),
            chosen_order.c.workflow_stage.label("latest_order_stage"),
        )
        .select_from(TelegramConversation)
        .outerjoin(order_stats, order_stats.c.conversation_id == TelegramConversation.id)
        .outerjoin(chosen_order, chosen_order.c.conversation_id == TelegramConversation.id)
        .cte("telegram_inbox_conversation_stages")
    )


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
    stage: Optional[str] = Query(default=None),
    chat_status: Optional[str] = Query(default=None, pattern="^(all|needs_admin|waiting_customer|ready_for_order)$"),
    status: Optional[str] = Query(default=None, pattern="^(all|needs_admin|waiting_customer|ready_for_order|archived)$"),
    q: Optional[str] = Query(default=None, max_length=120),
    cursor: Optional[str] = Query(default=None, max_length=512),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    # `status` is retained as a compatibility alias for old Inbox clients.
    if status == "archived" and stage is None:
        stage = "archived"
    elif status not in (None, "all", "archived") and chat_status is None:
        chat_status = status
    if chat_status == "all":
        chat_status = None
    if chat_status and chat_status not in {"needs_admin", "waiting_customer", "ready_for_order"}:
        raise _error(422, "invalid_chat_status")
    if stage:
        stage = normalize_workflow_filter_stage(stage)
        if stage not in set(WORKFLOW_FILTER_STAGES):
            raise _error(422, "invalid_workflow_stage")
    decoded_cursor = _cursor_decode(cursor) if cursor else None

    stage_rows = _conversation_stage_cte()
    filters = []
    if chat_status:
        filters.append(TelegramConversation.status == chat_status)
    if q and q.strip():
        needle = f"%{q.strip()}%"
        matching_order_conversations = select(Order.telegram_conversation_id).where(
            Order.telegram_conversation_id.is_not(None),
            Order.order_number.ilike(needle),
        )
        filters.append(
            or_(
                TelegramConversation.customer_name.ilike(needle),
                TelegramConversation.customer_username.ilike(needle),
                cast(TelegramConversation.chat_id, String).ilike(needle),
                TelegramConversation.id.in_(matching_order_conversations),
            )
        )

    filtered_rows = (
        select(
            stage_rows.c.conversation_id,
            stage_rows.c.workflow_stage,
        )
        .join(TelegramConversation, TelegramConversation.id == stage_rows.c.conversation_id)
        .where(*filters)
        .cte("telegram_inbox_filtered_conversations")
    )
    grouped_counts = (
        await session.execute(
            select(filtered_rows.c.workflow_stage, func.count(filtered_rows.c.conversation_id))
            .group_by(filtered_rows.c.workflow_stage)
        )
    ).all()
    counts = {key: 0 for key in WORKFLOW_FILTER_STAGES}
    for bucket, count in grouped_counts:
        counts[bucket] = int(count or 0)

    list_filters = [*filters]
    if stage:
        list_filters.append(stage_rows.c.workflow_stage == stage)
    if stage != "archived":
        list_filters.append(stage_rows.c.workflow_stage != "archived")

    if decoded_cursor:
        cursor_at, cursor_id = decoded_cursor
        list_filters.append(
            or_(
                TelegramConversation.last_message_at < cursor_at,
                and_(
                    TelegramConversation.last_message_at == cursor_at,
                    TelegramConversation.id < cursor_id,
                ),
            )
        )

    total = counts.get(stage, 0) if stage else sum(
        count for bucket, count in counts.items() if bucket != "archived"
    )

    rows = (
        await session.execute(
            select(
                TelegramConversation,
                stage_rows.c.workflow_stage,
                stage_rows.c.order_count,
                stage_rows.c.latest_order_number,
                stage_rows.c.latest_order_status,
                stage_rows.c.latest_order_archived_at,
                stage_rows.c.latest_order_created_at,
                stage_rows.c.latest_order_stage,
            )
            .join(stage_rows, stage_rows.c.conversation_id == TelegramConversation.id)
            .where(*list_filters)
            .order_by(TelegramConversation.last_message_at.desc(), TelegramConversation.id.desc())
            .limit(limit + 1)
        )
    ).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    conversation_ids = [row[0].id for row in rows]

    latest_messages: dict[str, TelegramInboxMessage] = {}
    if conversation_ids:
        ranked_messages = (
            select(
                TelegramInboxMessage.id.label("message_id"),
                func.row_number().over(
                    partition_by=TelegramInboxMessage.conversation_id,
                    order_by=(TelegramInboxMessage.created_at.desc(), TelegramInboxMessage.id.desc()),
                ).label("message_rank"),
            )
            .where(TelegramInboxMessage.conversation_id.in_(conversation_ids))
            .cte("telegram_inbox_latest_message_ids")
        )
        message_rows = (
            await session.execute(
                select(TelegramInboxMessage)
                .join(ranked_messages, ranked_messages.c.message_id == TelegramInboxMessage.id)
                .where(ranked_messages.c.message_rank == 1)
            )
        ).scalars().all()
        latest_messages = {message.conversation_id: message for message in message_rows}

    items = []
    for values in rows:
        row, resolved_stage, order_count, order_number, order_status, order_archived_at, order_created_at, order_stage = values
        latest_order = (
            {
                "order_number": order_number,
                "status": order_status,
                "stage": order_stage,
                "archived_at": order_archived_at,
                "created_at": order_created_at,
            }
            if order_number
            else None
        )
        items.append(
            _conversation_payload(
                row,
                latest_messages.get(row.id),
                workflow_stage=resolved_stage,
                order_count=int(order_count or 0),
                latest_order=latest_order,
            )
        )

    return {
        "items": items,
        "counts": counts,
        "total": total,
        "next_cursor": _cursor_encode(rows[-1][0]) if has_more and rows else None,
        "limit": limit,
    }


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(TelegramConversation, conversation_id)
    if not row:
        raise _error(404, "conversation_not_found")
    workflow_stage, order_count, latest_order, related_orders = await _conversation_order_context(session, row)
    message_rows = (
        await session.execute(
            select(TelegramInboxMessage)
            .where(TelegramInboxMessage.conversation_id == row.id)
            .order_by(TelegramInboxMessage.created_at.desc(), TelegramInboxMessage.id.desc())
            .limit(300)
        )
    ).scalars().all()
    messages = [_message_payload(message) for message in reversed(message_rows)]
    inbound_text = "\n".join(
        message.text.casefold()
        for message in message_rows
        if message.direction == "inbound" and not message.deleted_at
    )
    outbound_text = "\n".join(
        " ".join((message.text, str((message.rich_content or {}).get("intro") or ""))).casefold()
        for message in message_rows
        if message.direction == "outbound" and not message.deleted_at
    )
    inbound_references = {
        match.group(0).upper()
        for match in INQUIRY_REFERENCE_RE.finditer(inbound_text)
    }
    outbound_references = {
        match.group(0).upper()
        for match in INQUIRY_REFERENCE_RE.finditer(outbound_text)
    }
    if inbound_references:
        sent_inquiries = (
            await session.execute(
                select(TelegramCartInquiry)
                .where(
                    TelegramCartInquiry.telegram_connection_id == row.connection_id,
                    TelegramCartInquiry.telegram_chat_id == row.chat_id,
                    TelegramCartInquiry.source == "web",
                    TelegramCartInquiry.reference.in_(inbound_references),
                    TelegramCartInquiry.status == "sent",
                    TelegramCartInquiry.snapshot.is_not(None),
                    TelegramCartInquiry.delivered_at.is_not(None),
                )
                .order_by(TelegramCartInquiry.delivered_at.asc(), TelegramCartInquiry.id.asc())
            )
        ).scalars().all()
        for inquiry in sent_inquiries:
            if inquiry.reference.upper() not in outbound_references:
                messages.append(_reconstructed_cart_message(inquiry))
    messages.sort(
        key=lambda message: (
            message["created_at"],
            message.get("telegram_message_id") or 0,
            message["id"],
        )
    )
    candidates = (
        await session.execute(
            select(TelegramProductCandidate)
            .where(TelegramProductCandidate.conversation_id == row.id)
            .order_by(TelegramProductCandidate.created_at.desc())
        )
    ).scalars().all()
    connection = await session.get(TelegramBusinessConnection, row.connection_id)
    payload = _conversation_payload(
        row,
        message_rows[0] if message_rows else None,
        workflow_stage=workflow_stage,
        order_count=order_count,
        latest_order=latest_order,
    )
    payload["can_send"] = bool(
        payload["can_send"] and connection and connection.is_enabled and connection.can_reply
    )
    payload["messages"] = messages
    payload["orders"] = [
        {
            **_order_summary(order),
            "is_latest": bool(latest_order and order.order_number == latest_order["order_number"]),
        }
        for order in related_orders
    ]
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
    locale = data.get("locale")
    if locale is not None:
        row.locale = locale
        row.locale_source = "admin"
    for key, value in data.items():
        if key == "locale":
            continue
        setattr(row, key, value)
    await audit(session, user.id, "admin.telegram_inbox.conversation.update", "telegram_conversation", row.id, data)
    await session.commit()
    workflow_stage, order_count, latest_order, _ = await _conversation_order_context(session, row)
    return _conversation_payload(
        row,
        None,
        workflow_stage=workflow_stage,
        order_count=order_count,
        latest_order=latest_order,
    )


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
    media_index: Optional[int] = Query(default=None, ge=0),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(TelegramInboxMessage, message_id)
    if not row or row.deleted_at:
        raise _error(404, "telegram_photo_not_found")
    photo_file_id = row.photo_file_id
    photo_file_size = row.photo_file_size
    if media_index is not None:
        rich_content = row.rich_content if isinstance(row.rich_content, dict) else {}
        slides = rich_content.get("slides", [])
        slide = slides[media_index] if isinstance(slides, list) and media_index < len(slides) else None
        if not isinstance(slide, dict):
            raise _error(404, "telegram_photo_not_found")
        photo_file_id = slide.get("photo_file_id")
        photo_file_size = slide.get("photo_file_size")
    if not photo_file_id:
        raise _error(404, "telegram_photo_not_found")
    if photo_file_size and photo_file_size > MAX_CHAT_PHOTO_BYTES:
        raise _error(413, "telegram_photo_too_large")
    if not TELEGRAM_BOT_TOKEN:
        raise _error(503, "telegram_not_configured")
    try:
        file_info = await bot_request(
            TELEGRAM_BOT_TOKEN, "getFile", {"file_id": photo_file_id}
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
    locale = apply_direct_default_locale(conversation)
    translation = await session.scalar(
        select(ProductTranslation).where(
            ProductTranslation.product_id == product.id,
            ProductTranslation.locale == locale,
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
    caption = candidate_copy(locale, product_name, variant.sku, payload.quantity)
    markup = candidate_keyboard(token, locale)
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


@router.post("/{conversation_id}/pending-orders", status_code=201)
async def add_conversation_candidates_to_pending_orders(
    conversation_id: str,
    payload: InboxPendingOrderCreateIn,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    conversation = await _load_conversation(session, conversation_id)
    if not idempotency_key or not 16 <= len(idempotency_key) <= 80:
        raise _error(422, "invalid_idempotency_key")

    existing = await session.scalar(
        select(TelegramCartInquiry)
        .where(
            TelegramCartInquiry.source == "telegram_inbox",
            TelegramCartInquiry.conversation_id == conversation.id,
            TelegramCartInquiry.idempotency_key == idempotency_key,
        )
        .with_for_update()
    )
    if existing:
        return {"reference": existing.reference, "status": "pending_order"}

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
        raise _error(409, "only_confirmed_candidates_can_be_added_to_pending_orders")

    candidates_by_id = {candidate.id: candidate for candidate in candidates}
    items = []
    subtotal = 0
    currencies = set()
    for candidate_id in candidate_ids:
        candidate = candidates_by_id[candidate_id]
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
        ):
            raise _error(409, "catalog_item_unavailable", sku=candidate.sku)
        unit_price = _price(product, variant)
        line_total = unit_price * candidate.quantity
        subtotal += line_total
        currencies.add(product.currency)
        items.append(
            {
                "name": candidate.product_name,
                "sku": variant.sku,
                "quantity": candidate.quantity,
                "unit_price": unit_price,
                "line_total": line_total,
                "variant": _option_label(candidate.option_values or {}),
                "option_values": candidate.option_values or {},
                "image_url": candidate.image_url,
                "availability": "pre_order",
                "_candidate_id": candidate.id,
            }
        )
    if len(currencies) != 1:
        raise _error(409, "mixed_currency_order_unsupported")

    reference = f"SC-{secrets.token_hex(16).upper()}"
    inquiry = TelegramCartInquiry(
        reference=reference,
        cart_id=None,
        source="telegram_inbox",
        conversation_id=conversation.id,
        idempotency_key=idempotency_key,
        locale=conversation.locale,
        snapshot={
            "locale": conversation.locale,
            "items": items,
            "subtotal": subtotal,
            "currency": next(iter(currencies)),
            "item_count": sum(item["quantity"] for item in items),
            "_candidate_ids": candidate_ids,
            "_customer": {
                "name": conversation.customer_name,
                "username": conversation.customer_username,
            },
        },
        status="sent",
        telegram_connection_id=conversation.connection_id,
        telegram_chat_id=conversation.chat_id,
        delivered_at=utcnow(),
    )
    session.add(inquiry)
    for candidate in candidates:
        candidate.status = "pending_order"
    conversation.status = "waiting_customer"
    await audit(
        session,
        user.id,
        "admin.telegram_inbox.pending_order.create",
        "telegram_inquiry",
        reference,
        {"conversation_id": conversation.id, "candidate_ids": candidate_ids},
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        existing = await session.scalar(
            select(TelegramCartInquiry).where(
                TelegramCartInquiry.source == "telegram_inbox",
                TelegramCartInquiry.conversation_id == conversation.id,
                TelegramCartInquiry.idempotency_key == idempotency_key,
            )
        )
        if existing:
            return {"reference": existing.reference, "status": "pending_order"}
        raise _error(409, "pending_order_creation_conflict") from exc

    return {"reference": inquiry.reference, "status": "pending_order"}
