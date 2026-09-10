"""Checkout API — server-authoritative totals, idempotent order creation.

Guests check out with their secure guest cart (HttpOnly cookie); authenticated
users keep CSRF protection. Prices/shipping/totals are always recomputed
from PostgreSQL — the client sends only identity, address and choices.
"""

from urllib.parse import urlencode
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth import csrf_protect
from checkout import service as checkout_service
from checkout.service import CheckoutError
from config import (
    BASE_CURRENCY,
    CLICK_MODE,
    CLICK_RETURN_URL,
    FRONTEND_URL,
    INVENTORY_RESERVATION_TTL_MINUTES,
    RATE_LIMIT_BACKEND,
)
from db.models import Order, Payment, UserAddress
from db.session import get_session
from notifications import notify
from payments.providers import get_provider
from payments.service import PaymentService
from routers.auth import _client_ip
from routers.shop import _cart_payload, _find_cart, _optional_user
from shipping.factory import get_shipping_provider
from rate_limit import enforce_redis_limit

router = APIRouter(prefix="/api/v1/checkout", tags=["checkout"])

ORDER_RATE_LIMIT = 60
ORDER_RATE_WINDOW = 15 * 60
_order_hits: dict = {}


async def _rate_limit_orders(ip: str) -> None:
    if RATE_LIMIT_BACKEND == "redis":
        await enforce_redis_limit(
            "checkout-orders", ip, limit=ORDER_RATE_LIMIT, window_seconds=ORDER_RATE_WINDOW
        )
        return
    import time

    now = time.time()
    hits = [t for t in _order_hits.get(ip, []) if now - t < ORDER_RATE_WINDOW]
    if len(hits) >= ORDER_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="too_many_requests")
    hits.append(now)
    _order_hits[ip] = hits


class CheckoutAddressIn(BaseModel):
    recipient_name: str = Field(min_length=1, max_length=255)
    phone: str = Field(min_length=3, max_length=40)
    address_line_1: str = Field(min_length=3, max_length=255)
    address_line_2: Optional[str] = Field(default=None, max_length=255)
    city: str = Field(min_length=1, max_length=120)
    state_province: str = Field(min_length=1, max_length=120)
    postal_code: str = Field(min_length=2, max_length=20)
    country_code: str = Field(default="UZ", min_length=2, max_length=2)


class QuoteIn(BaseModel):
    shipping_method: str = Field(min_length=2, max_length=40)


class CheckoutOrderIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=80)
    shipping_method: str = Field(min_length=2, max_length=40)
    locale: str = Field(default="en", max_length=5)
    email: Optional[EmailStr] = None
    saved_address_id: Optional[str] = Field(default=None, min_length=8, max_length=40)
    address: Optional[CheckoutAddressIn] = None


ADDRESS_FIELDS = (
    "recipient_name",
    "phone",
    "address_line_1",
    "address_line_2",
    "city",
    "state_province",
    "postal_code",
    "country_code",
)


def _payment_return_url(order: Order, is_guest: bool) -> str:
    """Build the browser return URL used after the hosted payment flow."""

    base = CLICK_RETURN_URL or f"{FRONTEND_URL.rstrip('/')}/payment-pending"
    params = {"order": order.order_number}
    if is_guest and order.guest_access_token:
        params["token"] = order.guest_access_token
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}{urlencode(params)}"


def _order_out(
    order: Order,
    payment: Payment,
    is_guest: bool,
    payment_url: str | None = None,
) -> dict:
    out = {
        "order_number": order.order_number,
        "status": order.status,
        "payment_state": order.payment_state,
        "subtotal": order.subtotal,
        "shipping_amount": order.shipping_amount,
        "grand_total": order.grand_total,
        "currency": order.currency,
        "access_token": order.guest_access_token if is_guest else None,
        "payment": {
            "merchant_trans_id": payment.merchant_trans_id,
            "amount": payment.amount,
            "currency": payment.currency,
            "status": payment.status,
        },
    }
    if CLICK_MODE == "mock":
        url = (
            f"/checkout/payment/mock?order={order.order_number}"
            f"&payment={payment.merchant_trans_id}"
        )
        if is_guest and order.guest_access_token:
            url += f"&token={order.guest_access_token}"
        out["mock_payment_url"] = url
    elif payment_url:
        out["payment_url"] = payment_url
    return out


@router.get("/options")
async def checkout_options(
    request: Request, session: AsyncSession = Depends(get_session)
):
    user = await _optional_user(request, session)
    cart = await _find_cart(request, session, user)
    payload = await _cart_payload(session, cart)
    return {
        "currency": BASE_CURRENCY,
        "cart_subtotal": payload["subtotal"],
        "item_count": payload["item_count"],
        "items": payload["items"],
        "shipping_methods": get_shipping_provider().list_methods(payload["subtotal"]),
        "payment_methods": [{"code": "click", "label": "CLICK"}],
        "payment_mode": CLICK_MODE,
        "reservation_ttl_minutes": INVENTORY_RESERVATION_TTL_MINUTES,
    }


@router.post("/quote")
async def checkout_quote(
    payload: QuoteIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    user = await _optional_user(request, session)
    cart = await _find_cart(request, session, user)
    if not cart:
        raise HTTPException(status_code=400, detail="empty_cart")
    try:
        totals = await checkout_service.compute_cart_totals(
            session, cart, payload.shipping_method
        )
    except CheckoutError as exc:
        raise HTTPException(
            status_code=exc.status, detail={"error": exc.code, **exc.extra}
        )
    await session.commit()  # persists the lazy reservation-expiry sweep
    return {
        "subtotal": totals["subtotal"],
        "shipping_amount": totals["shipping_amount"],
        "grand_total": totals["grand_total"],
        "currency": totals["currency"],
        "shipping": totals["shipping"],
    }


@router.post("/orders", status_code=201)
async def create_checkout_order(
    payload: CheckoutOrderIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    await _rate_limit_orders(_client_ip(request))
    user = await _optional_user(request, session)
    cart = await _find_cart(request, session, user)
    if not cart:
        raise HTTPException(status_code=400, detail="empty_cart")
    request_user_id = user.id if user else None
    request_cart_id = cart.id

    if user:
        contact_email = user.email
    elif payload.email:
        contact_email = str(payload.email).lower()
    else:
        raise HTTPException(status_code=400, detail="email_required")

    if payload.saved_address_id:
        if not user:
            raise HTTPException(status_code=400, detail="address_required")
        saved = await session.scalar(
            select(UserAddress).where(
                UserAddress.id == payload.saved_address_id,
                UserAddress.user_id == user.id,
            )
        )
        if not saved:
            raise HTTPException(status_code=404, detail="address_not_found")
        address_snapshot = {k: getattr(saved, k) for k in ADDRESS_FIELDS}
    elif payload.address:
        address_snapshot = payload.address.model_dump()
    else:
        raise HTTPException(status_code=400, detail="address_required")

    try:
        order, created = await checkout_service.create_order(
            session,
            user=user,
            cart=cart,
            contact_email=contact_email,
            address_snapshot=address_snapshot,
            shipping_method=payload.shipping_method,
            idempotency_key=payload.idempotency_key,
            locale=payload.locale,
        )
        provider = get_provider()
        payment = await PaymentService(session, provider).create_payment(order)
        await session.commit()
    except CheckoutError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=exc.status, detail={"error": exc.code, **exc.extra}
        )
    except IntegrityError:
        # concurrent same-key submit lost the unique race — return the winner
        await session.rollback()
        order = await session.scalar(
            select(Order).where(Order.idempotency_key == payload.idempotency_key)
        )
        if not order:
            raise HTTPException(status_code=409, detail="order_conflict")
        try:
            checkout_service.ensure_idempotent_owner(
                order,
                user_id=request_user_id,
                cart_id=request_cart_id,
            )
        except CheckoutError as exc:
            raise HTTPException(
                status_code=exc.status, detail={"error": exc.code, **exc.extra}
            )
        payment = await session.scalar(
            select(Payment).where(Payment.order_id == order.id)
        )
        if not payment:
            raise HTTPException(status_code=409, detail="payment_conflict")
        created = False

    payment_url = None
    if CLICK_MODE != "mock":
        provider = get_provider()
        payment_url = provider.build_payment_url(
            payment.merchant_trans_id,
            payment.amount,
            return_url=_payment_return_url(order, is_guest=user is None),
        )

    if created:
        await notify(
            "order.placed",
            {
                "order_number": order.order_number,
                "email": contact_email,
                "amount": order.grand_total,
                "currency": order.currency,
            },
        )
    return _order_out(
        order,
        payment,
        is_guest=user is None,
        payment_url=payment_url,
    )
