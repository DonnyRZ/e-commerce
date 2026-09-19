"""Admin-controlled manual transfer orders and two-leg fulfillment.

This router deliberately does not enable public checkout. It turns a Telegram
cart inquiry into an order only after an authenticated operator supplies the
shipping details, then keeps payment and fulfillment transitions server-side.
"""

from __future__ import annotations

import hashlib
import mimetypes
import secrets
import uuid
from datetime import timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import csrf_protect, require_roles
from checkout.service import _reserved_quantities, expire_due_reservations
from cms.service import audit
from config import (
    APP_ENV,
    FRONTEND_URL,
    PAYMENT_EVIDENCE_MAX_BYTES,
    SUPPLIER_TO_ADMIN_TRANSIT_DAYS,
    TELEGRAM_BOT_TOKEN,
)
from db.models import (
    InventoryReservation,
    ManualPaymentEvidence,
    CmsAuditLog,
    Order,
    OrderFulfillmentStage,
    OrderItem,
    Payment,
    Product,
    ProductVariant,
    TelegramCartInquiry,
    User,
    utcnow,
)
from db.session import get_session
from storage.payment_evidence import delete as delete_evidence_file
from storage.payment_evidence import resolve as resolve_evidence_file
from storage.payment_evidence import save as save_evidence_file
from telegram_inquiries import bot_request

router = APIRouter(prefix="/api/v1", tags=["manual-orders"])
require_admin = require_roles("admin")

ORDER_STAGES = {
    "supplier_shipping": {"from": "paid", "to": "supplier_shipping"},
    "received_by_admin": {"from": "supplier_shipping", "to": "received_by_admin"},
    "customer_shipping": {"from": "received_by_admin", "to": "customer_shipping"},
    "delivered": {"from": "customer_shipping", "to": "delivered"},
}
WORKFLOW_STAGES = (
    "inquiry",
    "pending_payment",
    "payment_review",
    "paid",
    "supplier_shipping",
    "received_by_admin",
    "customer_shipping",
    "delivered",
)
ACTIONABLE_ORDER_STATUSES = {
    "pending_payment",
    "payment_review",
    "paid",
    "supplier_shipping",
    "received_by_admin",
    "customer_shipping",
    "processing",
    "shipped",
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
    }.get(stage, "view_order")


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


def _stage_payload(stage: OrderFulfillmentStage) -> dict:
    return {
        "stage": stage.stage,
        "status": stage.status,
        "carrier": stage.carrier,
        "tracking_number": stage.tracking_number,
        "shipped_at": stage.shipped_at,
        "received_at": stage.received_at,
        "expected_at": stage.expected_at,
        "note": stage.note,
    }


async def _notify_order(
    inquiry_id: Optional[str], text: str, session: AsyncSession
) -> None:
    """Best-effort Telegram notification; never rolls back an order mutation."""
    if not inquiry_id or not TELEGRAM_BOT_TOKEN:
        return
    inquiry = await session.scalar(
        select(TelegramCartInquiry).where(TelegramCartInquiry.id == inquiry_id)
    )
    if (
        not inquiry
        or not inquiry.telegram_connection_id
        or not inquiry.telegram_chat_id
    ):
        return
    try:
        await bot_request(
            TELEGRAM_BOT_TOKEN,
            "sendMessage",
            {
                "business_connection_id": inquiry.telegram_connection_id,
                "chat_id": inquiry.telegram_chat_id,
                "text": text[:3900],
            },
        )
    except Exception:
        # Notification failure is observable through the audit trail/API but
        # must never undo a verified payment or fulfillment transition.
        return


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


async def _load_admin_order(order_number: str, session: AsyncSession) -> Order:
    order = await session.scalar(
        select(Order).where(Order.order_number == order_number).with_for_update()
    )
    if not order:
        raise _error(404, "order_not_found")
    return order


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
    if stage and stage not in WORKFLOW_STAGES:
        raise _error(422, "invalid_workflow_stage")

    entries: list[dict] = []
    inquiry_query = select(TelegramCartInquiry).where(
        TelegramCartInquiry.order_id.is_(None),
        TelegramCartInquiry.status.in_(["pending", "sending", "sent"]),
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
    for inquiry in inquiries:
        if inquiry.expires_at <= utcnow():
            continue
        snapshot = inquiry.snapshot or {}
        snapshot_items = snapshot.get("items") or []
        if not snapshot_items:
            continue
        if stage and stage != "inquiry":
            continue
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

    order_query = select(Order)
    if q:
        like = f"%{q}%"
        order_query = order_query.where(
            or_(
                Order.order_number.ilike(like),
                Order.guest_email.ilike(like),
            )
        )
    if scope == "actionable":
        order_query = order_query.where(Order.status.in_(ACTIONABLE_ORDER_STATUSES))
    if stage:
        if stage == "inquiry":
            order_query = order_query.where(Order.id == "__no_order__")
        else:
            order_query = order_query.where(Order.status == stage)
    orders = (
        (await session.execute(order_query.order_by(Order.created_at.desc())))
        .scalars()
        .all()
    )
    for order in orders:
        items_count = await session.scalar(
            select(func.count(OrderItem.id)).where(OrderItem.order_id == order.id)
        )
        address = order.shipping_address or {}
        linked_user = await session.get(User, order.user_id) if order.user_id else None
        normalized_stage = order.status if order.status in WORKFLOW_STAGES else order.status
        entries.append(
            {
                "kind": "order",
                "order_number": order.order_number,
                "order_source": order.order_source,
                "stage": normalized_stage,
                "status": order.status,
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
                "next_action": _workflow_next_action(normalized_stage),
            }
        )

    entries.sort(key=lambda item: item["created_at"], reverse=True)
    counts = {key: 0 for key in WORKFLOW_STAGES}
    for entry in entries:
        if entry["stage"] in counts:
            counts[entry["stage"]] += 1
    total = len(entries)
    start = (page - 1) * page_size
    return {
        "items": entries[start:start + page_size],
        "counts": counts,
        "total": total,
        "page": page,
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
    tracking_link = (
        f"{FRONTEND_URL}/orders/track?order_number={order.order_number}&token={order.guest_access_token}"
        if order.guest_access_token
        else f"{FRONTEND_URL}/orders/{order.order_number}"
    )
    await _notify_order(
        inquiry.id,
        (
            f"Order {order.order_number} dibuat. Total: {order.grand_total:,} "
            f"{order.currency}. Lihat status: {tracking_link}"
        ),
        session,
    )
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
    payment.status = "pending_review"
    payment.failure_code = None
    payment.failure_note = None
    payment.review_note = None
    order.payment_state = "review"
    order.status = "payment_review"
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
    if payment.status != "pending_review":
        raise _error(409, "payment_evidence_required")
    items = (
        (
            await session.execute(
                select(OrderItem)
                .where(OrderItem.order_id == order.id)
                .order_by(OrderItem.variant_id)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    variant_ids = sorted({item.variant_id for item in items if item.variant_id})
    variants = {}
    for variant_id in variant_ids:
        variants[variant_id] = await session.scalar(
            select(ProductVariant)
            .where(ProductVariant.id == variant_id)
            .with_for_update()
        )
    await expire_due_reservations(session)
    reserved = await _reserved_quantities(session, variant_ids)
    committed = (
        (
            await session.execute(
                select(InventoryReservation).where(
                    InventoryReservation.order_id == order.id,
                    InventoryReservation.status == "committed",
                )
            )
        )
        .scalars()
        .all()
    )
    if committed:
        raise _error(409, "inventory_already_committed")
    for item in items:
        variant = variants.get(item.variant_id)
        if not variant:
            raise _error(409, "catalog_item_missing", sku=item.sku)
        active_other = reserved.get(variant.id, 0)
        if variant.stock_quantity - active_other < item.quantity:
            raise _error(
                409,
                "insufficient_stock",
                sku=item.sku,
                available=max(0, variant.stock_quantity - active_other),
            )
    now = utcnow()
    for item in items:
        variant = variants[item.variant_id]
        variant.stock_quantity -= item.quantity
        session.add(
            InventoryReservation(
                order_id=order.id,
                product_variant_id=variant.id,
                quantity=item.quantity,
                status="committed",
                expires_at=now,
                committed_at=now,
            )
        )
    payment.status = "paid"
    payment.paid_at = now
    payment.reviewed_by = user.id
    payment.reviewed_at = now
    payment.review_note = "Manual transfer verified by admin"
    order.payment_state = "paid"
    order.status = "paid"
    await audit(
        session,
        user.id,
        "admin.payment.confirm",
        "payment",
        payment.id,
        {"order": order.order_number},
    )
    await session.commit()
    await _notify_order(
        await _inquiry_id_for_order(session, order.id),
        f"Pembayaran order {order.order_number} telah dikonfirmasi. Pesanan sedang diproses.",
        session,
    )
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
    await audit(
        session,
        user.id,
        "admin.payment.reject",
        "payment",
        payment.id,
        {"reason": payload.reason},
    )
    await session.commit()
    await _notify_order(
        await _inquiry_id_for_order(session, order.id),
        f"Bukti pembayaran order {order.order_number} belum dapat diverifikasi. Alasan: {payload.reason}",
        session,
    )
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
    order.status = transition["to"]
    await audit(
        session,
        user.id,
        "admin.order.fulfillment",
        "order",
        order.order_number,
        {"stage": payload.stage, "tracking": payload.tracking_number},
    )
    await session.commit()
    labels = {
        "supplier_shipping": "Barang dikirim menuju admin",
        "received_by_admin": "Barang diterima admin",
        "customer_shipping": "Barang dikirim ke customer",
        "delivered": "Barang diterima customer",
    }
    await _notify_order(
        await _inquiry_id_for_order(session, order.id),
        f"Update order {order.order_number}: {labels[payload.stage]}.",
        session,
    )
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
        "payment_state": order.payment_state,
        "order_source": order.order_source,
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
                "evidence": [_evidence_payload(item) for item in evidence],
            }
            if payment
            else None
        ),
        "fulfillment": [_stage_payload(stage) for stage in stages],
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
