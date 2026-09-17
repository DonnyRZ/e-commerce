"""Cart + Wishlist routes.

Ownership model:
- authenticated: cart/wishlist bound to user.id (JWT cookie)
- guest: cart bound to a server-issued 32-byte opaque token in an
  HttpOnly cookie (guest_cart_token) — never accepted from the client
  as a parameter, never guessable.
Cart is intent, not inventory reservation: stock is validated on
mutations but never decremented here.
"""

import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import COOKIE_SAMESITE, COOKIE_SECURE, csrf_protect, decode_token, get_current_user
from db.models import (
    Cart,
    CartItem,
    Category,
    Product,
    ProductTranslation,
    ProductVariant,
    User,
    Wishlist,
    WishlistItem,
)
from db.session import get_session
from media import media_item_url

router = APIRouter(prefix="/api/v1", tags=["shop"])

GUEST_COOKIE = "guest_cart_token"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


async def _optional_user(request: Request, session: AsyncSession) -> Optional[User]:
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = decode_token(token, "access")
    except Exception:
        return None
    user = await session.get(User, payload.get("sub") or "")
    return user if user and user.is_active else None


async def _find_cart(request: Request, session: AsyncSession, user: Optional[User]) -> Optional[Cart]:
    if user:
        return await session.scalar(select(Cart).where(Cart.user_id == user.id))
    token = request.cookies.get(GUEST_COOKIE)
    if not token:
        return None
    return await session.scalar(select(Cart).where(Cart.guest_token == token))


async def _get_or_create_cart(
    request: Request, response: Response, session: AsyncSession, user: Optional[User]
) -> Cart:
    cart = await _find_cart(request, session, user)
    if cart:
        return cart
    if user:
        cart = Cart(user_id=user.id)
    else:
        token = secrets.token_urlsafe(32)
        cart = Cart(guest_token=token)
        response.set_cookie(
            GUEST_COOKIE,
            token,
            max_age=30 * 24 * 3600,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite=COOKIE_SAMESITE,
            path="/",
        )
    session.add(cart)
    await session.flush()
    return cart


async def _cart_payload(session: AsyncSession, cart: Optional[Cart]) -> dict:
    if not cart:
        return {"id": None, "items": [], "subtotal": 0, "currency": "UZS", "item_count": 0}
    rows = (
        await session.execute(
            select(CartItem).where(CartItem.cart_id == cart.id).order_by(CartItem.id)
        )
    ).scalars().all()
    items = []
    subtotal = 0
    for row in rows:
        product = (
            await session.execute(
                select(Product).where(Product.id == row.product_id)
            )
        ).scalar_one_or_none()
        variant = await session.get(ProductVariant, row.variant_id)
        translations = {}
        if product:
            trs = (
                await session.execute(
                    select(ProductTranslation).where(
                        ProductTranslation.product_id == product.id
                    )
                )
            ).scalars().all()
            translations = {t.locale: {"title": t.name} for t in trs}
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
        if not product or not variant or not category:
            unit_price = 0
            compare_at = None
            availability = "unavailable"
            stock = 0
            sku = ""
            options = {}
            image = None
        else:
            unit_price = (
                variant.sale_price_override
                or variant.price_override
                or product.base_price
            )
            compare_at = (
                (variant.price_override or product.base_price)
                if variant.sale_price_override
                else product.compare_at_price
            )
            stock = variant.stock_quantity
            sku = variant.sku
            options = variant.option_values or {}
            image = variant.image_url or media_item_url((product.media or [None])[0])
            if not variant.is_active or product.status != "active" or not category:
                availability = "unavailable"
            elif stock <= 0:
                availability = "out_of_stock"
            elif row.quantity > stock:
                availability = "exceeds_stock"
            elif stock <= 5:
                availability = "low_stock"
            else:
                availability = "in_stock"
        subtotal += unit_price * row.quantity
        items.append(
            {
                "id": row.id,
                "product_id": row.product_id,
                "variant_id": row.variant_id,
                "slug": product.slug if product else "",
                "translations": translations,
                "brand": product.brand if product else "",
                "image_url": image,
                "option_values": options,
                "sku": sku,
                "quantity": row.quantity,
                "unit_price": unit_price,
                "compare_at_price": compare_at,
                "line_total": unit_price * row.quantity,
                "stock_quantity": stock,
                "availability": availability,
            }
        )
    return {
        "id": cart.id,
        "items": items,
        "subtotal": subtotal,
        "currency": "UZS",
        "item_count": sum(i["quantity"] for i in items),
    }


async def _owned_cart_item(
    item_id: str, request: Request, session: AsyncSession, user: Optional[User]
) -> CartItem:
    item = await session.get(CartItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="item_not_found")
    cart = await session.get(Cart, item.cart_id)
    if user:
        ok = cart and cart.user_id == user.id
    else:
        ok = cart and cart.guest_token and cart.guest_token == request.cookies.get(GUEST_COOKIE)
    if not ok:
        raise HTTPException(status_code=404, detail="item_not_found")
    return item


# --------------------------------------------------------------------------
# cart
# --------------------------------------------------------------------------


class CartItemIn(BaseModel):
    product_id: str = Field(min_length=8, max_length=40)
    variant_id: str = Field(min_length=8, max_length=40)
    quantity: int = Field(default=1, ge=1, le=99)


class CartItemUpdateIn(BaseModel):
    quantity: int = Field(ge=1, le=99)


@router.get("/cart")
async def get_cart(request: Request, session: AsyncSession = Depends(get_session)):
    user = await _optional_user(request, session)
    cart = await _find_cart(request, session, user)
    return await _cart_payload(session, cart)


@router.post("/cart/items", status_code=201)
async def add_cart_item(
    payload: CartItemIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    user = await _optional_user(request, session)
    product = await session.get(Product, payload.product_id)
    if not product or product.status != "active":
        raise HTTPException(status_code=404, detail="product_not_found")
    # Showcase products remain addable so visitors can exercise the cart while
    # checkout is disabled. The checkout service still rejects demo products,
    # and the checkout endpoints are currently fail-closed, so this can never
    # create a sellable order.
    category = await session.scalar(
        select(Category).where(
            Category.id == product.category_id,
            Category.kind == "category",
            Category.is_active.is_(True),
        )
    )
    if not category:
        raise HTTPException(status_code=404, detail="product_not_found")
    variant = await session.get(ProductVariant, payload.variant_id)
    if not variant or variant.product_id != product.id or not variant.is_active:
        raise HTTPException(status_code=400, detail="invalid_variant")
    if variant.stock_quantity <= 0:
        raise HTTPException(
            status_code=400,
            detail={"error": "insufficient_stock", "available": 0},
        )
    cart = await _get_or_create_cart(request, response, session, user)
    # Row lock on the cart prevents racing same-variant merges.
    await session.scalar(select(Cart.id).where(Cart.id == cart.id).with_for_update())
    existing = await session.scalar(
        select(CartItem).where(
            CartItem.cart_id == cart.id, CartItem.variant_id == variant.id
        )
    )
    current = existing.quantity if existing else 0
    new_qty = current + payload.quantity
    if new_qty > variant.stock_quantity:
        raise HTTPException(
            status_code=400,
            detail={"error": "insufficient_stock", "available": variant.stock_quantity, "in_cart": current},
        )
    if existing:
        existing.quantity = new_qty
    else:
        session.add(
            CartItem(
                cart_id=cart.id,
                product_id=product.id,
                variant_id=variant.id,
                quantity=payload.quantity,
            )
        )
    await session.commit()
    return await _cart_payload(session, cart)


@router.patch("/cart/items/{item_id}")
async def update_cart_item(
    item_id: str,
    payload: CartItemUpdateIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    user = await _optional_user(request, session)
    item = await _owned_cart_item(item_id, request, session, user)
    variant = await session.get(ProductVariant, item.variant_id)
    if variant and payload.quantity > variant.stock_quantity:
        raise HTTPException(
            status_code=400,
            detail={"error": "insufficient_stock", "available": variant.stock_quantity},
        )
    item.quantity = payload.quantity
    await session.commit()
    cart = await session.get(Cart, item.cart_id)
    return await _cart_payload(session, cart)


@router.delete("/cart/items/{item_id}", status_code=204)
async def remove_cart_item(
    item_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    user = await _optional_user(request, session)
    item = await _owned_cart_item(item_id, request, session, user)
    await session.delete(item)
    await session.commit()
    return None


@router.delete("/cart", status_code=204)
async def clear_cart(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    user = await _optional_user(request, session)
    cart = await _find_cart(request, session, user)
    if cart:
        await session.execute(delete(CartItem).where(CartItem.cart_id == cart.id))
        await session.commit()
    return None


@router.post("/cart/merge")
async def merge_guest_cart(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    token = request.cookies.get(GUEST_COOKIE)
    guest_cart = (
        await session.scalar(select(Cart).where(Cart.guest_token == token))
        if token
        else None
    )
    if not guest_cart:
        user_cart = await session.scalar(select(Cart).where(Cart.user_id == user.id))
        return {**(await _cart_payload(session, user_cart)), "adjustments": []}

    user_cart = await session.scalar(select(Cart).where(Cart.user_id == user.id))
    if not user_cart:
        user_cart = Cart(user_id=user.id)
        session.add(user_cart)
        await session.flush()
    await session.scalar(select(Cart.id).where(Cart.id == user_cart.id).with_for_update())

    adjustments = []
    guest_items = (
        await session.execute(select(CartItem).where(CartItem.cart_id == guest_cart.id))
    ).scalars().all()
    for g in guest_items:
        variant = await session.get(ProductVariant, g.variant_id)
        if not variant or not variant.is_active or variant.stock_quantity <= 0:
            adjustments.append({"variant_id": g.variant_id, "requested": g.quantity, "applied": 0})
            continue
        existing = await session.scalar(
            select(CartItem).where(
                CartItem.cart_id == user_cart.id, CartItem.variant_id == g.variant_id
            )
        )
        merged = (existing.quantity if existing else 0) + g.quantity
        applied = min(merged, variant.stock_quantity)
        if applied != merged:
            adjustments.append({"variant_id": g.variant_id, "requested": merged, "applied": applied})
        if existing:
            existing.quantity = applied
        else:
            session.add(
                CartItem(
                    cart_id=user_cart.id,
                    product_id=g.product_id,
                    variant_id=g.variant_id,
                    quantity=applied,
                )
            )
    await session.delete(guest_cart)
    response.delete_cookie(GUEST_COOKIE, path="/", secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE)
    await session.commit()
    return {**(await _cart_payload(session, user_cart)), "adjustments": adjustments}


# --------------------------------------------------------------------------
# wishlist (authenticated only)
# --------------------------------------------------------------------------


class WishlistItemIn(BaseModel):
    product_id: str = Field(min_length=8, max_length=40)


async def _get_or_create_wishlist(session: AsyncSession, user: User) -> Wishlist:
    wishlist = await session.scalar(select(Wishlist).where(Wishlist.user_id == user.id))
    if not wishlist:
        wishlist = Wishlist(user_id=user.id)
        session.add(wishlist)
        await session.flush()
    return wishlist


async def _wishlist_payload(session: AsyncSession, user: User) -> dict:
    wishlist = await session.scalar(select(Wishlist).where(Wishlist.user_id == user.id))
    if not wishlist:
        return {"items": [], "count": 0}
    rows = (
        await session.execute(
            select(WishlistItem)
            .where(WishlistItem.wishlist_id == wishlist.id)
            .order_by(WishlistItem.id)
        )
    ).scalars().all()
    items = []
    for row in rows:
        product = await session.get(Product, row.product_id)
        if not product:
            continue
        trs = (
            await session.execute(
                select(ProductTranslation).where(
                    ProductTranslation.product_id == product.id
                )
            )
        ).scalars().all()
        stock = await session.scalar(
            select(ProductVariant.stock_quantity).where(
                ProductVariant.product_id == product.id,
                ProductVariant.is_active.is_(True),
            )
        )
        total_stock = (
            await session.execute(
                select(ProductVariant.stock_quantity).where(
                    ProductVariant.product_id == product.id,
                    ProductVariant.is_active.is_(True),
                )
            )
        ).scalars().all()
        total = sum(total_stock)
        items.append(
            {
                "product_id": product.id,
                "slug": product.slug,
                "translations": {t.locale: {"title": t.name} for t in trs},
                "brand": product.brand,
                "base_price": product.base_price,
                "compare_at_price": product.compare_at_price,
                "image_url": media_item_url((product.media or [None])[0]),
                "stock_state": "out_of_stock" if total <= 0 else ("low_stock" if total <= 5 else "in_stock"),
            }
        )
    return {"items": items, "count": len(items)}


@router.get("/wishlist")
async def get_wishlist(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await _wishlist_payload(session, user)


@router.post("/wishlist/items", status_code=201)
async def add_wishlist_item(
    payload: WishlistItemIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    product = await session.get(Product, payload.product_id)
    if not product or product.status != "active":
        raise HTTPException(status_code=404, detail="product_not_found")
    category = await session.scalar(
        select(Category).where(
            Category.id == product.category_id,
            Category.kind == "category",
            Category.is_active.is_(True),
        )
    )
    if not category:
        raise HTTPException(status_code=404, detail="product_not_found")
    wishlist = await _get_or_create_wishlist(session, user)
    existing = await session.scalar(
        select(WishlistItem).where(
            WishlistItem.wishlist_id == wishlist.id,
            WishlistItem.product_id == product.id,
        )
    )
    if not existing:
        session.add(WishlistItem(wishlist_id=wishlist.id, product_id=product.id))
    await session.commit()
    return await _wishlist_payload(session, user)


@router.delete("/wishlist/items/{product_id}")
async def remove_wishlist_item(
    product_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    wishlist = await session.scalar(select(Wishlist).where(Wishlist.user_id == user.id))
    if wishlist:
        await session.execute(
            delete(WishlistItem).where(
                WishlistItem.wishlist_id == wishlist.id,
                WishlistItem.product_id == product_id,
            )
        )
        await session.commit()
    return await _wishlist_payload(session, user)
