"""Cart + Wishlist routes.

Ownership model:
- authenticated: cart/wishlist bound to user.id (JWT cookie)
- guest: cart bound to a server-issued 32-byte opaque token in an
  HttpOnly cookie (guest_cart_token) — never accepted from the client
  as a parameter, never guessable.
Cart is intent, not inventory reservation. All storefront items are
pre-order items; internal stock is never used to block cart mutations.
"""

import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import COOKIE_SAMESITE, COOKIE_SECURE, csrf_protect, decode_token, require_roles
from config import PREORDER_ESTIMATE_DAYS
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
from taxonomy import active_taxonomy_chain

router = APIRouter(prefix="/api/v1", tags=["shop"])

GUEST_COOKIE = "guest_cart_token"
PREORDER_MAX_QUANTITY = 99


def _positive_quantity(value) -> int:
    """Normalize legacy cart integers without allowing bool/negative values."""

    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
        else 0
    )


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


async def _optional_user(request: Request, session: AsyncSession) -> Optional[User]:
    token = request.cookies.get("access_token")
    if not token:
        header = request.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            token = header[7:].strip()
    if not token:
        return None
    # A present-but-invalid access token is not a guest session. Return 401 so
    # the client can refresh it (or clear a revoked session) instead of
    # silently switching a signed-in customer to the guest cart.
    payload = decode_token(token, "access")
    user = await session.get(User, payload.get("sub") or "")
    if not user or not user.is_active or payload.get("ver", 0) != user.token_version:
        raise HTTPException(status_code=401, detail="session_expired")
    if user.role != "customer":
        # An authenticated operator/seller must never be silently downgraded
        # to a guest cart. That would let a non-customer session create and
        # mutate state on a customer-facing surface by omission.
        raise HTTPException(status_code=403, detail="forbidden")
    return user


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
    if user:
        # Serialize the read-then-create path. The partial unique index still
        # protects integrity, but the lock avoids leaking an IntegrityError to
        # a legitimate pair of concurrent first-add requests.
        await session.scalar(
            select(User.id).where(User.id == user.id).with_for_update()
        )
    guest_token = request.cookies.get(GUEST_COOKIE) if not user else None
    if guest_token:
        # A guest cart has no user row to act as a serialization point. Lock
        # on the opaque token before the read-then-create path so two tabs
        # using an existing guest cookie cannot create duplicate carts.
        await session.scalar(
            select(
                func.pg_advisory_xact_lock(
                    func.hashtext(f"cart:guest:{guest_token}")
                )
            )
        )
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
        raw_quantity = row.quantity
        quantity = _positive_quantity(raw_quantity)
        quantity_is_valid = quantity >= 1
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
        category_is_public = bool(
            category and await active_taxonomy_chain(session, category)
        )
        size_available_for_new_orders = bool(
            category_is_public
            and product
            and product.status == "active"
            and variant
            and variant.product_id == product.id
            and variant.is_active
        )
        if (
            not quantity_is_valid
            or
            not product
            or not variant
            or variant.product_id != product.id
            or not category_is_public
            or product.status != "active"
            or not variant.is_active
        ):
            unit_price = 0
            compare_at = None
            availability = "invalid" if not quantity_is_valid else "unavailable"
            stock = 0
            sku = ""
            options = {}
            image = None
        else:
            regular_price = (
                variant.price_override
                if variant.price_override is not None
                else product.base_price
            )
            unit_price = (
                variant.sale_price_override
                if variant.sale_price_override is not None
                else regular_price
            )
            compare_at = (
                regular_price
                if variant.sale_price_override is not None
                else product.compare_at_price
            )
            stock = max(int(variant.stock_quantity or 0), 0)
            sku = variant.sku
            options = variant.option_values or {}
            image = variant.image_url or media_item_url((product.media or [None])[0])
            availability = "pre_order"
        subtotal += unit_price * quantity
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
                "quantity": quantity,
                "unit_price": unit_price,
                "compare_at_price": compare_at,
                "line_total": unit_price * quantity,
                "stock_quantity": stock,
                "availability": availability,
                "ordering_mode": "pre_order",
                "preorder_estimate_days": PREORDER_ESTIMATE_DAYS,
                "size_available_for_new_orders": size_available_for_new_orders,
                "can_increase_quantity": (
                    size_available_for_new_orders
                    and quantity < PREORDER_MAX_QUANTITY
                    and availability == "pre_order"
                ),
                # Kept for legacy API clients; never use this to gate or
                # describe customer ordering availability.
                "is_demo": False,
                "cart_max_quantity": PREORDER_MAX_QUANTITY,
            }
        )
    return {
        "id": cart.id,
        "items": items,
        "subtotal": subtotal,
        "currency": "UZS",
        "item_count": sum(max(i["quantity"], 0) for i in items),
    }


async def _owned_cart_item(
    item_id: str,
    request: Request,
    session: AsyncSession,
    user: Optional[User],
    *,
    lock: bool = False,
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
    if lock:
        # All cart mutations use the cart row as the serialization point. The
        # item is re-read after the lock so an overlapping delete cannot cause
        # a stale quantity update or a lost update.
        locked_cart = await session.scalar(
            select(Cart).where(Cart.id == cart.id).with_for_update()
        )
        item = await session.scalar(
            select(CartItem)
            .where(CartItem.id == item_id, CartItem.cart_id == locked_cart.id)
            .with_for_update()
        ) if locked_cart else None
        if not item:
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
async def get_cart(
    request: Request,
    guest: bool = False,
    session: AsyncSession = Depends(get_session),
):
    user = None if guest else await _optional_user(request, session)
    cart = await _find_cart(request, session, user)
    return await _cart_payload(session, cart)


@router.post("/cart/items", status_code=201)
async def add_cart_item(
    payload: CartItemIn,
    request: Request,
    response: Response,
    guest: bool = False,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    user = None if guest else await _optional_user(request, session)
    product = await session.get(Product, payload.product_id)
    if not product or product.status != "active":
        raise HTTPException(status_code=404, detail="product_not_found")
    cart = await _get_or_create_cart(request, response, session, user)
    # Row lock on the cart prevents racing same-variant merges.
    locked_cart = await session.scalar(
        select(Cart).where(Cart.id == cart.id).with_for_update()
    )
    if not locked_cart:
        # A login merge can delete a guest cart after the initial lookup. Do
        # not continue with a detached cart object and risk a misleading
        # foreign-key error or an item written to the wrong cart.
        raise HTTPException(status_code=409, detail="cart_changed")
    cart = locked_cart
    # Showcase products remain addable so visitors can exercise the cart while
    # checkout is disabled. Re-read all catalog rows after the cart lock so a
    # concurrent admin edit cannot leave a newly-added item pointing at an
    # inactive product, variant, or taxonomy chain.
    product = await session.scalar(
        select(Product).where(Product.id == payload.product_id).with_for_update()
    )
    category = (
        await session.scalar(
            select(Category)
            .where(Category.id == product.category_id)
            .with_for_update()
        )
        if product
        else None
    )
    variant = await session.scalar(
        select(ProductVariant)
        .where(
            ProductVariant.id == payload.variant_id,
            ProductVariant.product_id == payload.product_id,
        )
        .with_for_update()
    )
    if (
        not product
        or product.status != "active"
        or not category
        or category.kind != "category"
        or not category.is_active
        or not await active_taxonomy_chain(session, category, lock=True)
    ):
        raise HTTPException(status_code=404, detail="product_not_found")
    if not variant or not variant.is_active:
        raise HTTPException(status_code=400, detail="invalid_variant")
    existing = await session.scalar(
        select(CartItem).where(
            CartItem.cart_id == cart.id, CartItem.variant_id == variant.id
        )
    )
    if existing and existing.product_id != product.id:
        raise HTTPException(status_code=409, detail="cart_item_conflict")
    current = _positive_quantity(existing.quantity) if existing else 0
    new_qty = current + payload.quantity
    if new_qty > PREORDER_MAX_QUANTITY:
        raise HTTPException(
            status_code=400,
            detail={"error": "quantity_limit", "maximum": PREORDER_MAX_QUANTITY, "in_cart": current},
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
    guest: bool = False,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    user = None if guest else await _optional_user(request, session)
    item = await _owned_cart_item(item_id, request, session, user, lock=True)
    product = await session.scalar(
        select(Product).where(Product.id == item.product_id).with_for_update()
    )
    category = (
        await session.scalar(
            select(Category)
            .where(Category.id == product.category_id)
            .with_for_update()
        )
        if product
        else None
    )
    if (
        not category
        or category.kind != "category"
        or not category.is_active
        or not await active_taxonomy_chain(session, category, lock=True)
    ):
        raise HTTPException(status_code=404, detail="item_not_found")
    variant = await session.scalar(
        select(ProductVariant)
        .where(
            ProductVariant.id == item.variant_id,
            ProductVariant.product_id == item.product_id,
        )
        .with_for_update()
    )
    if (
        not product
        or product.status != "active"
        or not variant
        or variant.product_id != product.id
        or not variant.is_active
    ):
        raise HTTPException(status_code=404, detail="item_not_found")
    if payload.quantity > PREORDER_MAX_QUANTITY:
        raise HTTPException(
            status_code=400,
            detail={"error": "quantity_limit", "maximum": PREORDER_MAX_QUANTITY},
        )
    item.quantity = payload.quantity
    await session.commit()
    cart = await session.get(Cart, item.cart_id)
    return await _cart_payload(session, cart)


@router.delete("/cart/items/{item_id}", status_code=204)
async def remove_cart_item(
    item_id: str,
    request: Request,
    guest: bool = False,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    user = None if guest else await _optional_user(request, session)
    item = await _owned_cart_item(item_id, request, session, user, lock=True)
    await session.delete(item)
    await session.commit()
    return None


@router.delete("/cart", status_code=204)
async def clear_cart(
    request: Request,
    guest: bool = False,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    user = None if guest else await _optional_user(request, session)
    cart = await _find_cart(request, session, user)
    if cart:
        locked_cart = await session.scalar(
            select(Cart).where(Cart.id == cart.id).with_for_update()
        )
        if locked_cart:
            await session.execute(
                delete(CartItem).where(CartItem.cart_id == locked_cart.id)
            )
            await session.commit()
    return None


@router.post("/cart/merge")
async def merge_guest_cart(
    request: Request,
    response: Response,
    user: User = Depends(require_roles("customer")),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    # Keep the lock order deterministic (user -> guest cart -> user cart) so a
    # simultaneous login merge and cart mutation cannot deadlock.
    await session.scalar(select(User.id).where(User.id == user.id).with_for_update())
    token = request.cookies.get(GUEST_COOKIE)
    guest_cart = (
        await session.scalar(
            select(Cart).where(Cart.guest_token == token).with_for_update()
        )
        if token
        else None
    )
    if not guest_cart:
        user_cart = await session.scalar(
            select(Cart).where(Cart.user_id == user.id).with_for_update()
        )
        return {**(await _cart_payload(session, user_cart)), "adjustments": []}

    user_cart = await session.scalar(
        select(Cart).where(Cart.user_id == user.id).with_for_update()
    )
    if not user_cart:
        user_cart = Cart(user_id=user.id)
        session.add(user_cart)
        await session.flush()
    adjustments = []
    guest_items = (
        await session.execute(
            select(CartItem)
            .where(CartItem.cart_id == guest_cart.id)
            .with_for_update()
        )
    ).scalars().all()
    for g in guest_items:
        guest_quantity = _positive_quantity(g.quantity)
        if guest_quantity < 1:
            adjustments.append(
                {"variant_id": g.variant_id, "requested": guest_quantity, "applied": 0}
            )
            continue
        product = await session.scalar(
            select(Product).where(Product.id == g.product_id).with_for_update()
        )
        category = (
            await session.scalar(
                select(Category)
                .where(Category.id == product.category_id)
                .with_for_update()
            )
            if product
            else None
        )
        variant = await session.scalar(
            select(ProductVariant)
            .where(
                ProductVariant.id == g.variant_id,
                ProductVariant.product_id == g.product_id,
            )
            .with_for_update()
        )
        if (
            not product
            or product.status != "active"
            or not variant
            or variant.product_id != product.id
            or not variant.is_active
            or not category
            or category.kind != "category"
            or not category.is_active
            or not await active_taxonomy_chain(session, category, lock=True)
        ):
            adjustments.append(
                {"variant_id": g.variant_id, "requested": guest_quantity, "applied": 0}
            )
            continue
        existing = await session.scalar(
            select(CartItem).where(
                CartItem.cart_id == user_cart.id, CartItem.variant_id == g.variant_id
            )
        )
        existing_quantity = _positive_quantity(existing.quantity) if existing else 0
        merged = existing_quantity + guest_quantity
        applied = min(merged, PREORDER_MAX_QUANTITY)
        if applied != merged:
            adjustments.append({"variant_id": g.variant_id, "requested": merged, "applied": applied, "reason": "quantity_limit"})
        if existing:
            if existing.product_id != product.id:
                existing.product_id = product.id
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
    # Wishlist creation and item insertion are protected by the same owner
    # lock. This keeps the database uniqueness rule from surfacing as a 500
    # when two browser tabs add the first item at the same time.
    await session.scalar(select(User.id).where(User.id == user.id).with_for_update())
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
        if not product or product.status != "active":
            continue
        category = await session.scalar(
            select(Category).where(
                Category.id == product.category_id,
                Category.kind == "category",
                Category.is_active.is_(True),
            )
        )
        # A product can be unpublished after it was saved. Do not return
        # private/dangling catalog data that would render a broken public
        # product link; the wishlist row remains harmless historical state.
        if not category or not await active_taxonomy_chain(session, category):
            continue
        trs = (
            await session.execute(
                select(ProductTranslation).where(
                    ProductTranslation.product_id == product.id
                )
            )
        ).scalars().all()
        items.append(
            {
                "product_id": product.id,
                "slug": product.slug,
                "translations": {t.locale: {"title": t.name} for t in trs},
                "brand": product.brand,
                "base_price": product.base_price,
                "compare_at_price": product.compare_at_price,
                "image_url": media_item_url((product.media or [None])[0]),
                "stock_state": "pre_order",
            }
        )
    return {"items": items, "count": len(items)}


@router.get("/wishlist")
async def get_wishlist(
    user: User = Depends(require_roles("customer")),
    session: AsyncSession = Depends(get_session),
):
    return await _wishlist_payload(session, user)


@router.post("/wishlist/items", status_code=201)
async def add_wishlist_item(
    payload: WishlistItemIn,
    user: User = Depends(require_roles("customer")),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    product = await session.scalar(
        select(Product).where(Product.id == payload.product_id).with_for_update()
    )
    if not product or product.status != "active":
        raise HTTPException(status_code=404, detail="product_not_found")
    category = await session.scalar(
        select(Category).where(
            Category.id == product.category_id,
            Category.kind == "category",
            Category.is_active.is_(True),
        )
    )
    if not category or not await active_taxonomy_chain(session, category):
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
    user: User = Depends(require_roles("customer")),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    # Match add/create locking so a concurrent toggle cannot be overwritten
    # by a stale read of the wishlist row.
    await session.scalar(select(User.id).where(User.id == user.id).with_for_update())
    wishlist = await session.scalar(
        select(Wishlist).where(Wishlist.user_id == user.id).with_for_update()
    )
    if wishlist:
        await session.execute(
            delete(WishlistItem).where(
                WishlistItem.wishlist_id == wishlist.id,
                WishlistItem.product_id == product_id,
            )
        )
        await session.commit()
    return await _wishlist_payload(session, user)
