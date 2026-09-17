"""Checkout domain service — server-authoritative totals, order creation,
inventory reservation lifecycle.

Reservation strategy (single consistent model):
- physical stock is NOT reduced at reservation time
- availability = stock_quantity - SUM(active reservations)
- on payment success: lock reservation + variant rows, decrement stock once,
  mark reservation committed
- on payment failure/cancel/expiry: active reservations -> released
- TTL expiry: lazy sweep marks overdue active reservations expired
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import BASE_CURRENCY, CHECKOUT_ENABLED, INVENTORY_RESERVATION_TTL_MINUTES
from db.models import (
    Cart,
    CartItem,
    Category,
    InventoryReservation,
    Order,
    OrderItem,
    Product,
    ProductTranslation,
    ProductVariant,
    SellerOrderFulfillment,
    User,
)
from media import media_item_url
from shipping.factory import get_shipping_provider
from shipping.mock import UnknownShippingMethod


class CheckoutError(Exception):
    def __init__(self, code: str, status: int = 400, extra: Optional[dict] = None):
        super().__init__(code)
        self.code = code
        self.status = status
        self.extra = extra or {}


def ensure_idempotent_owner(
    order: Order,
    *,
    user_id: Optional[str],
    cart_id: str,
) -> None:
    """Prevent an idempotency key from replaying another customer's order."""

    if order.user_id != user_id or order.cart_id != cart_id:
        raise CheckoutError("idempotency_key_conflict", 409)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def expire_due_reservations(
    session: AsyncSession, now: Optional[datetime] = None
) -> None:
    now = now or _now()
    await session.execute(
        update(InventoryReservation)
        .where(
            InventoryReservation.status == "active",
            InventoryReservation.expires_at <= now,
        )
        .values(status="expired", released_at=now)
    )


async def _reserved_quantities(session: AsyncSession, variant_ids) -> dict:
    if not variant_ids:
        return {}
    rows = await session.execute(
        select(
            InventoryReservation.product_variant_id,
            func.coalesce(func.sum(InventoryReservation.quantity), 0),
        )
        .where(
            InventoryReservation.product_variant_id.in_(variant_ids),
            InventoryReservation.status == "active",
        )
        .group_by(InventoryReservation.product_variant_id)
    )
    return {vid: int(qty) for vid, qty in rows.all()}


async def compute_cart_totals(
    session: AsyncSession,
    cart: Cart,
    shipping_method_code: Optional[str] = None,
    lock: bool = False,
) -> dict:
    """Recalculate everything from the DB. The client never supplies prices."""
    await expire_due_reservations(session)
    rows = (
        await session.execute(
            select(CartItem).where(CartItem.cart_id == cart.id).order_by(CartItem.id)
        )
    ).scalars().all()
    if not rows:
        raise CheckoutError("empty_cart", 400)
    variant_ids = sorted({r.variant_id for r in rows})
    variant_query = (
        select(ProductVariant)
        .where(ProductVariant.id.in_(variant_ids))
        .order_by(ProductVariant.id)
    )
    if lock:
        variant_query = variant_query.with_for_update()
    variants = {
        v.id: v for v in (await session.execute(variant_query)).scalars().all()
    }
    reserved = await _reserved_quantities(session, variant_ids)
    items = []
    subtotal = 0
    for row in rows:
        variant = variants.get(row.variant_id)
        product = await session.get(Product, row.product_id) if variant else None
        category = (
            await session.scalar(
                select(Category).where(
                    Category.id == product.category_id,
                    Category.kind == "category",
                    Category.is_active.is_(True),
                )
            )
            if product
            else None
        )
        if (
            not variant
            or not variant.is_active
            or not product
            or product.status != "active"
            or product.is_demo
            or not category
        ):
            raise CheckoutError("unavailable_item", 409, {"variant_id": row.variant_id})
        available = variant.stock_quantity - reserved.get(variant.id, 0)
        if row.quantity > available:
            raise CheckoutError(
                "insufficient_stock",
                409,
                {
                    "variant_id": variant.id,
                    "sku": variant.sku,
                    "available": max(available, 0),
                },
            )
        unit_price = (
            variant.sale_price_override
            or variant.price_override
            or product.base_price
        )
        items.append(
            {
                "row": row,
                "variant": variant,
                "product": product,
                "unit_price": unit_price,
                "line_total": unit_price * row.quantity,
            }
        )
        subtotal += unit_price * row.quantity
    shipping = None
    shipping_amount = 0
    if shipping_method_code:
        try:
            shipping = get_shipping_provider().quote(shipping_method_code, subtotal)
        except UnknownShippingMethod:
            raise CheckoutError("invalid_shipping_method", 400)
        shipping_amount = shipping["amount"]
    return {
        "items": items,
        "subtotal": subtotal,
        "shipping": shipping,
        "shipping_amount": shipping_amount,
        "grand_total": subtotal + shipping_amount,
        "currency": BASE_CURRENCY,
    }


async def _localized_name(session: AsyncSession, product: Product, locale: str) -> str:
    trs = (
        await session.execute(
            select(ProductTranslation).where(
                ProductTranslation.product_id == product.id
            )
        )
    ).scalars().all()
    names = {t.locale: t.name for t in trs}
    return names.get(locale) or names.get("en") or product.slug


async def create_order(
    session: AsyncSession,
    *,
    user: Optional[User],
    cart: Cart,
    contact_email: str,
    address_snapshot: dict,
    shipping_method: str,
    idempotency_key: str,
    locale: str,
):
    """Idempotent: an existing order with the same key is returned unchanged."""
    if not CHECKOUT_ENABLED:
        raise CheckoutError(
            "checkout_unavailable",
            503,
            {"message": "Online checkout is temporarily unavailable."},
        )
    existing = await session.scalar(
        select(Order).where(Order.idempotency_key == idempotency_key)
    )
    if existing:
        ensure_idempotent_owner(
            existing,
            user_id=user.id if user else None,
            cart_id=cart.id,
        )
        return existing, False
    totals = await compute_cart_totals(session, cart, shipping_method, lock=True)
    now = _now()
    order = Order(
        order_number=f"MC-{uuid.uuid4().hex[:10].upper()}",
        user_id=user.id if user else None,
        guest_email=contact_email,  # customer email snapshot (guest or auth)
        guest_access_token=None if user else secrets.token_urlsafe(24),
        cart_id=cart.id,
        shipping_address=address_snapshot,
        shipping_method=totals["shipping"]["code"],
        subtotal=totals["subtotal"],
        shipping_amount=totals["shipping_amount"],
        grand_total=totals["grand_total"],
        currency=BASE_CURRENCY,
        payment_state="unpaid",
        status="pending_payment",
        idempotency_key=idempotency_key,
    )
    session.add(order)
    await session.flush()
    expires_at = now + timedelta(minutes=INVENTORY_RESERVATION_TTL_MINUTES)
    for item in totals["items"]:
        product, variant, row = item["product"], item["variant"], item["row"]
        session.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                variant_id=variant.id,
                seller_id=product.seller_id,
                sku=variant.sku,
                product_name=await _localized_name(session, product, locale),
                option_values=variant.option_values or {},
                image_url=variant.image_url or media_item_url((product.media or [None])[0]),
                unit_price=item["unit_price"],
                quantity=row.quantity,
                line_total=item["line_total"],
            )
        )
        session.add(
            InventoryReservation(
                order_id=order.id,
                product_variant_id=variant.id,
                quantity=row.quantity,
                status="active",
                expires_at=expires_at,
            )
        )
    # one seller-scoped fulfillment row per participating seller
    for seller_id in sorted({item["product"].seller_id for item in totals["items"]}):
        session.add(SellerOrderFulfillment(order_id=order.id, seller_id=seller_id))
    await session.flush()
    return order, True


# Explicit reconciliation states (centralized — do not scatter raw strings)
ORDER_STATUS_PAYMENT_REVIEW = "payment_review"
ORDER_PAYMENT_STATE_REVIEW = "review"


async def reconcile_paid_effects(session: AsyncSession, order: Order) -> bool:
    """Commit inventory for a successfully Completed payment — atomically.

    HARD RULE: only reservations still `active` commit directly.
    Expired/released reservations are NEVER reactivated or committed;
    instead stock is reacquired under row locks and an auditable
    replacement reservation (reacquired_from -> original row) is created.
    If any quantity cannot be reacquired, NOTHING is applied and False is
    returned so the caller can route payment/order into explicit
    reconciliation states instead of overselling.
    """
    now = _now()
    reservations = (
        await session.execute(
            select(InventoryReservation)
            .where(InventoryReservation.order_id == order.id)
            .order_by(InventoryReservation.product_variant_id)
            .with_for_update()
        )
    ).scalars().all()
    to_commit = [r for r in reservations if r.status == "active"]
    to_reacquire = [r for r in reservations if r.status in ("expired", "released")]

    variant_ids = sorted({r.product_variant_id for r in to_commit + to_reacquire})
    variants = {}
    for vid in variant_ids:  # deterministic lock order
        variants[vid] = await session.scalar(
            select(ProductVariant)
            .where(ProductVariant.id == vid)
            .with_for_update()
        )

    # Phase 1: feasibility check only — nothing mutates before this passes.
    planned_reacq: dict = {}
    for r in to_reacquire:
        variant = variants.get(r.product_variant_id)
        if not variant:
            return False
        active_reserved = await _reserved_quantities(session, [r.product_variant_id])
        # active_reserved already includes this order's own active rows, which
        # will also decrement stock — so only prior reacquisitions are extra.
        available = (
            variant.stock_quantity
            - active_reserved.get(r.product_variant_id, 0)
            - planned_reacq.get(r.product_variant_id, 0)
        )
        if r.quantity > available:
            return False
        planned_reacq[r.product_variant_id] = (
            planned_reacq.get(r.product_variant_id, 0) + r.quantity
        )

    # Phase 2: apply. Committed rows are excluded from both lists on any
    # retry, so repeated calls can never double-decrement.
    for r in to_commit:
        variant = variants.get(r.product_variant_id)
        if variant:
            variant.stock_quantity -= r.quantity
        r.status = "committed"
        r.committed_at = now
    for r in to_reacquire:
        variant = variants[r.product_variant_id]
        variant.stock_quantity -= r.quantity
        # historical expired/released row stays untouched — auditable trail
        session.add(
            InventoryReservation(
                order_id=order.id,
                product_variant_id=r.product_variant_id,
                quantity=r.quantity,
                status="committed",
                expires_at=now,
                committed_at=now,
                reacquired_from=r.id,
            )
        )
    return True


async def release_reservations(session: AsyncSession, order_id: str) -> None:
    now = _now()
    await session.execute(
        update(InventoryReservation)
        .where(
            InventoryReservation.order_id == order_id,
            InventoryReservation.status == "active",
        )
        .values(status="released", released_at=now)
    )


async def clear_source_cart(session: AsyncSession, order: Order) -> None:
    """Clear ONLY the cart that produced this order. DELETE is idempotent."""
    if order.cart_id:
        await session.execute(delete(CartItem).where(CartItem.cart_id == order.cart_id))
