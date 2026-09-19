"""Customer order history/detail + privacy-safe guest order lookup.

Guest orders are readable only with order_number + opaque guest_access_token
(constant-time compare). Auth orders are ownership-scoped; user A can never
read user B's order.
"""

import hmac

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import require_roles
from db.models import Order, OrderFulfillmentStage, OrderItem, User
from db.session import get_session

router = APIRouter(prefix="/api/v1", tags=["orders"])
require_customer = require_roles("customer")


def _item_out(item: OrderItem) -> dict:
    return {
        "product_id": item.product_id,
        "variant_id": item.variant_id,
        "seller_id": item.seller_id,
        "sku": item.sku,
        "product_name": item.product_name,
        "option_values": item.option_values or {},
        "image_url": item.image_url,
        "unit_price": item.unit_price,
        "quantity": item.quantity,
        "line_total": item.line_total,
    }


def _summary(order: Order, item_count: int) -> dict:
    return {
        "order_number": order.order_number,
        "created_at": order.created_at,
        "status": order.status,
        "payment_state": order.payment_state,
        "grand_total": order.grand_total,
        "currency": order.currency,
        "item_count": item_count,
    }


def _detail(order: Order, items) -> dict:
    return {
        **_summary(order, len(items)),
        "email": order.guest_email,
        "subtotal": order.subtotal,
        "shipping_amount": order.shipping_amount,
        "shipping_method": order.shipping_method,
        "shipping_address": order.shipping_address or {},
        "items": [_item_out(i) for i in items],
    }


async def _timeline(session: AsyncSession, order: Order) -> list[dict]:
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
    result = [
        {
            "stage": "pending_payment",
            "status": "completed" if order.status != "pending_payment" else "current",
        }
    ]
    if order.status in {
        "payment_review",
        "paid",
        "supplier_shipping",
        "received_by_admin",
        "customer_shipping",
        "delivered",
    }:
        result.append(
            {
                "stage": "payment_review",
                "status": "completed" if order.payment_state == "paid" else "current",
            }
        )
    for stage in stages:
        result.append(
            {
                "stage": stage.stage,
                "status": stage.status,
                "carrier": stage.carrier,
                "tracking_number": stage.tracking_number,
                "shipped_at": stage.shipped_at,
                "received_at": stage.received_at,
                "expected_at": stage.expected_at,
            }
        )
    return result


async def _items(session: AsyncSession, order_id: str):
    return (
        (
            await session.execute(
                select(OrderItem)
                .where(OrderItem.order_id == order_id)
                .order_by(OrderItem.id)
            )
        )
        .scalars()
        .all()
    )


@router.get("/account/orders")
async def list_my_orders(
    user: User = Depends(require_customer),
    session: AsyncSession = Depends(get_session),
):
    orders = (
        (
            await session.execute(
                select(Order)
                .where(Order.user_id == user.id)
                .order_by(Order.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    result = []
    for order in orders:
        count = await session.scalar(
            select(func.count(OrderItem.id)).where(OrderItem.order_id == order.id)
        )
        result.append(_summary(order, int(count or 0)))
    return result


@router.get("/account/orders/{order_number}")
async def get_my_order(
    order_number: str,
    user: User = Depends(require_customer),
    session: AsyncSession = Depends(get_session),
):
    order = await session.scalar(
        select(Order).where(
            Order.order_number == order_number, Order.user_id == user.id
        )
    )
    if not order:
        raise HTTPException(status_code=404, detail="order_not_found")
    payload = _detail(order, await _items(session, order.id))
    payload["timeline"] = await _timeline(session, order)
    return payload


@router.get("/orders/track")
async def track_guest_order(
    order_number: str = Query(min_length=4, max_length=40),
    token: str = Query(min_length=8, max_length=80),
    session: AsyncSession = Depends(get_session),
):
    order = await session.scalar(
        select(Order).where(Order.order_number == order_number)
    )
    ok = (
        order is not None
        and order.user_id is None
        and order.guest_access_token is not None
        and hmac.compare_digest(token, order.guest_access_token)
    )
    if not ok:
        raise HTTPException(status_code=404, detail="order_not_found")
    payload = _detail(order, await _items(session, order.id))
    payload["timeline"] = await _timeline(session, order)
    return payload


@router.get("/orders/{order_number}/timeline")
async def get_order_timeline(
    order_number: str,
    user: User = Depends(require_customer),
    session: AsyncSession = Depends(get_session),
):
    order = await session.scalar(
        select(Order).where(
            Order.order_number == order_number, Order.user_id == user.id
        )
    )
    if not order:
        raise HTTPException(status_code=404, detail="order_not_found")
    return {
        "order_number": order.order_number,
        "status": order.status,
        "timeline": await _timeline(session, order),
    }
