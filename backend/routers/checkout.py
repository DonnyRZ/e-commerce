"""Checkout API while the store has no configured payment method.

Cart operations remain available through the shop API. Checkout endpoints
remain explicit and fail closed until a real payment workflow is selected and
implemented; this prevents accidental orders and inventory reservations.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from auth import csrf_protect
from config import BASE_CURRENCY, CHECKOUT_ENABLED, INVENTORY_RESERVATION_TTL_MINUTES
from db.session import get_session
from routers.shop import _cart_payload, _find_cart, _optional_user
from shipping.factory import get_shipping_provider

router = APIRouter(prefix="/api/v1/checkout", tags=["checkout"])


def _require_checkout_enabled() -> None:
    if not CHECKOUT_ENABLED:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "checkout_unavailable",
                "message": "Online checkout is temporarily unavailable.",
            },
        )


async def _checkout_write_guard(request: Request) -> None:
    """Fail closed before CSRF checks or any future checkout mutation."""
    _require_checkout_enabled()
    await csrf_protect(request)


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


@router.get("/options")
async def checkout_options(
    request: Request,
    guest: bool = False,
    session: AsyncSession = Depends(get_session),
):
    user = None if guest else await _optional_user(request, session)
    cart = await _find_cart(request, session, user)
    payload = await _cart_payload(session, cart)
    return {
        "currency": BASE_CURRENCY,
        "cart_subtotal": payload["subtotal"],
        "item_count": payload["item_count"],
        "items": payload["items"],
        "shipping_methods": get_shipping_provider().list_methods(payload["subtotal"]),
        "payment_methods": [],
        "payment_mode": "disabled",
        "checkout_enabled": False,
        "reservation_ttl_minutes": INVENTORY_RESERVATION_TTL_MINUTES,
    }


@router.post("/quote")
async def checkout_quote(
    payload: QuoteIn,
    _: None = Depends(_checkout_write_guard),
):
    _require_checkout_enabled()
    # The guard above is deliberately unconditional in the current release.
    # Keep the endpoint shape for the future payment workflow.
    return None


@router.post("/orders", status_code=201)
async def create_checkout_order(
    payload: CheckoutOrderIn,
    _: None = Depends(_checkout_write_guard),
):
    _require_checkout_enabled()
    # The guard above is deliberately unconditional in the current release.
    # Keep the endpoint shape for the future payment workflow.
    return None
