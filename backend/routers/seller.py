"""Seller marketplace API — strict backend ownership scoping.

Every query is ownership-constrained (WHERE seller_id = current seller);
cross-seller access returns 404 (no existence leak). seller_id always comes
from the authenticated identity — client-supplied seller_id is never read.
Reservations remain system-controlled; sellers edit physical stock only,
never below active reservation commitments.
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth import require_roles
from checkout.service import _reserved_quantities
from db.models import (
    Category,
    Order,
    OrderItem,
    Product,
    ProductTranslation,
    ProductVariant,
    SellerOrderFulfillment,
    SellerProfile,
    User,
)
from db.session import get_session

router = APIRouter(prefix="/api/v1/seller", tags=["seller"])

require_seller = require_roles("seller")

LOCALES = {"id", "en", "uz", "ru"}
PRODUCT_STATUSES = {"draft", "active", "inactive"}
LOW_STOCK_THRESHOLD = 5  # mirrors routers/catalog.py

FULFILLMENT_STATUSES = {"pending", "processing", "shipped", "delivered", "cancelled"}
FULFILLMENT_TRANSITIONS = {
    "pending": {"processing"},
    "processing": {"shipped"},
    "shipped": {"delivered"},
    "delivered": set(),
    "cancelled": set(),
}

_UNSAFE_TEXT = re.compile(r"[<>]")


def _now():
    return datetime.now(timezone.utc)


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:80] or "product"


def _stock_state(total: int) -> str:
    if total <= 0:
        return "out_of_stock"
    if total <= LOW_STOCK_THRESHOLD:
        return "low_stock"
    return "in_stock"


def _bad_request(code: str, extra: Optional[dict] = None):
    raise HTTPException(status_code=400, detail={"error": code, **(extra or {})})


# ------------------------------- schemas ---------------------------------
# Mass-assignment safe: no seller_id / ownership / merchandising fields.


class TranslationIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    short_description: Optional[str] = Field(default=None, max_length=500)
    description: Optional[str] = Field(default=None, max_length=10000)


class VariantIn(BaseModel):
    sku: str = Field(min_length=2, max_length=80)
    option_values: dict = Field(default_factory=dict)
    stock_quantity: int = Field(default=0, ge=0)
    price_override: Optional[int] = Field(default=None, ge=0)
    sale_price_override: Optional[int] = Field(default=None, ge=0)
    image_url: Optional[str] = Field(default=None, max_length=500)
    is_active: bool = True


class ProductCreateIn(BaseModel):
    category_id: str = Field(min_length=8, max_length=40)
    product_type: str = Field(default="general", max_length=20)
    brand: str = Field(default="", max_length=120)
    base_price: int = Field(ge=0)
    compare_at_price: Optional[int] = Field(default=None, ge=0)
    status: str = Field(default="draft")
    attributes: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    media: list[dict] = Field(default_factory=list)
    translations: dict[str, TranslationIn]
    variants: list[VariantIn] = Field(min_length=1)


class ProductUpdateIn(BaseModel):
    category_id: Optional[str] = Field(default=None, min_length=8, max_length=40)
    product_type: Optional[str] = Field(default=None, max_length=20)
    brand: Optional[str] = Field(default=None, max_length=120)
    base_price: Optional[int] = Field(default=None, ge=0)
    compare_at_price: Optional[int] = Field(default=None, ge=0)
    status: Optional[str] = None
    attributes: Optional[dict] = None
    tags: Optional[list[str]] = None
    media: Optional[list[dict]] = None
    translations: Optional[dict[str, TranslationIn]] = None


class VariantUpdateIn(BaseModel):
    sku: Optional[str] = Field(default=None, min_length=2, max_length=80)
    option_values: Optional[dict] = None
    price_override: Optional[int] = Field(default=None, ge=0)
    sale_price_override: Optional[int] = Field(default=None, ge=0)
    image_url: Optional[str] = Field(default=None, max_length=500)
    is_active: Optional[bool] = None


class InventoryIn(BaseModel):
    stock_quantity: int = Field(ge=0)


class FulfillmentIn(BaseModel):
    status: str
    tracking_number: Optional[str] = Field(default=None, max_length=120)
    shipping_carrier: Optional[str] = Field(default=None, max_length=80)


class ProfileIn(BaseModel):
    store_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    contact_phone: Optional[str] = Field(default=None, max_length=40)


# ------------------------------- helpers ---------------------------------


async def _own_product(session: AsyncSession, product_id: str, seller_id: str) -> Product:
    product = await session.scalar(
        select(Product).where(Product.id == product_id, Product.seller_id == seller_id)
    )
    if not product:
        raise HTTPException(status_code=404, detail="product_not_found")
    return product


async def _own_variant(session: AsyncSession, variant_id: str, seller_id: str) -> ProductVariant:
    variant = await session.scalar(
        select(ProductVariant)
        .join(Product, ProductVariant.product_id == Product.id)
        .where(ProductVariant.id == variant_id, Product.seller_id == seller_id)
    )
    if not variant:
        raise HTTPException(status_code=404, detail="variant_not_found")
    return variant


def _validate_translations(translations: dict, require_en: bool) -> None:
    unknown = set(translations) - LOCALES
    if unknown:
        _bad_request("invalid_locale", {"locales": sorted(unknown)})
    if require_en and "en" not in translations:
        _bad_request("translation_en_required")


async def _check_skus(session: AsyncSession, skus: list[str], exclude_variant_id: Optional[str] = None) -> None:
    dupes = {s for s in skus if skus.count(s) > 1}
    if dupes:
        raise HTTPException(status_code=409, detail={"error": "sku_duplicate_in_payload", "skus": sorted(dupes)})
    query = select(ProductVariant.sku).where(ProductVariant.sku.in_(skus))
    if exclude_variant_id:
        query = query.where(ProductVariant.id != exclude_variant_id)
    taken = (await session.execute(query)).scalars().all()
    if taken:
        raise HTTPException(status_code=409, detail={"error": "sku_exists", "skus": sorted(taken)})


async def _validate_category(session: AsyncSession, category_id: str) -> None:
    category = await session.scalar(
        select(Category).where(Category.id == category_id, Category.is_active == True)
    )
    if not category:
        _bad_request("invalid_category")


def _validate_media(media: list[dict]) -> None:
    if len(media) > 8:
        _bad_request("too_many_media")
    for m in media:
        url = (m or {}).get("url", "")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")) or len(url) > 500:
            _bad_request("invalid_media_url")


def _translation_map(translations) -> dict:
    return {
        t.locale: {
            "name": t.name,
            "short_description": t.short_description,
            "description": t.description,
        }
        for t in translations
    }


async def _product_payload(session: AsyncSession, product: Product) -> dict:
    translations = (
        await session.execute(
            select(ProductTranslation).where(ProductTranslation.product_id == product.id)
        )
    ).scalars().all()
    variants = (
        await session.execute(
            select(ProductVariant)
            .where(ProductVariant.product_id == product.id)
            .order_by(ProductVariant.sku)
        )
    ).scalars().all()
    reserved = await _reserved_quantities(session, [v.id for v in variants])
    return {
        "id": product.id,
        "slug": product.slug,
        "category_id": product.category_id,
        "product_type": product.product_type,
        "brand": product.brand,
        "base_price": product.base_price,
        "compare_at_price": product.compare_at_price,
        "currency": product.currency,
        "status": product.status,
        "attributes": product.attributes or {},
        "tags": product.tags or [],
        "media": product.media or [],
        "translations": _translation_map(translations),
        "variants": [
            {
                "id": v.id,
                "sku": v.sku,
                "option_values": v.option_values or {},
                "stock_quantity": v.stock_quantity,
                "active_reserved": reserved.get(v.id, 0),
                "available": v.stock_quantity - reserved.get(v.id, 0),
                "price_override": v.price_override,
                "sale_price_override": v.sale_price_override,
                "image_url": v.image_url,
                "is_active": v.is_active,
                "stock_state": _stock_state(v.stock_quantity),
            }
            for v in variants
        ],
    }


# ------------------------------- dashboard --------------------------------


@router.get("/dashboard")
async def seller_dashboard(
    user: User = Depends(require_seller),
    session: AsyncSession = Depends(get_session),
):
    product_rows = (
        await session.execute(
            select(Product.id, Product.status).where(Product.seller_id == user.id)
        )
    ).all()
    product_ids = [p.id for p in product_rows]
    active_products = sum(1 for p in product_rows if p.status == "active")

    low_stock = out_of_stock = 0
    if product_ids:
        variant_stocks = (
            await session.execute(
                select(ProductVariant.stock_quantity).where(
                    ProductVariant.product_id.in_(product_ids),
                    ProductVariant.is_active == True,
                )
            )
        ).scalars().all()
        low_stock = sum(1 for s in variant_stocks if 0 < s <= LOW_STOCK_THRESHOLD)
        out_of_stock = sum(1 for s in variant_stocks if s == 0)

    fulfillment_counts = (
        await session.execute(
            select(SellerOrderFulfillment.status, func.count())
            .where(SellerOrderFulfillment.seller_id == user.id)
            .group_by(SellerOrderFulfillment.status)
        )
    ).all()
    fulfillments = {status: count for status, count in fulfillment_counts}

    # seller-attributable sales: own line totals on paid orders only.
    # Labelled "sales" — NOT a withdrawable balance (payouts deferred).
    sales = (
        await session.execute(
            select(
                func.coalesce(func.sum(OrderItem.line_total), 0),
                func.count(func.distinct(OrderItem.order_id)),
            )
            .join(Order, OrderItem.order_id == Order.id)
            .where(OrderItem.seller_id == user.id, Order.payment_state == "paid")
        )
    ).one()

    recent = (
        await session.execute(
            select(SellerOrderFulfillment, Order)
            .join(Order, SellerOrderFulfillment.order_id == Order.id)
            .where(SellerOrderFulfillment.seller_id == user.id)
            .order_by(Order.created_at.desc())
            .limit(5)
        )
    ).all()
    recent_orders = []
    for fulfillment, order in recent:
        agg = (
            await session.execute(
                select(func.count(), func.coalesce(func.sum(OrderItem.line_total), 0))
                .where(OrderItem.order_id == order.id, OrderItem.seller_id == user.id)
            )
        ).one()
        recent_orders.append(
            {
                "order_number": order.order_number,
                "created_at": order.created_at,
                "payment_state": order.payment_state,
                "fulfillment_status": fulfillment.status,
                "item_count": int(agg[0]),
                "seller_subtotal": int(agg[1]),
            }
        )

    return {
        "active_products": active_products,
        "total_products": len(product_ids),
        "low_stock_variants": low_stock,
        "out_of_stock_variants": out_of_stock,
        "pending_fulfillments": fulfillments.get("pending", 0),
        "processing_fulfillments": fulfillments.get("processing", 0),
        "sales_total": int(sales[0]),
        "sales_order_count": int(sales[1]),
        "currency": "UZS",
        "recent_orders": recent_orders,
    }


# ------------------------------- products ---------------------------------


@router.get("/products")
async def list_products(
    user: User = Depends(require_seller),
    session: AsyncSession = Depends(get_session),
    q: Optional[str] = Query(default=None, max_length=120),
    status: Optional[str] = Query(default=None),
    category_id: Optional[str] = Query(default=None),
    inventory: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    locale: str = Query(default="en", max_length=5),
):
    stock_sq = (
        select(
            ProductVariant.product_id.label("pid"),
            func.coalesce(func.sum(ProductVariant.stock_quantity), 0).label("total"),
            func.count(ProductVariant.id).label("variant_count"),
        )
        .where(ProductVariant.is_active == True)
        .group_by(ProductVariant.product_id)
        .subquery()
    )
    base = (
        select(Product, func.coalesce(stock_sq.c.total, 0), func.coalesce(stock_sq.c.variant_count, 0))
        .outerjoin(stock_sq, stock_sq.c.pid == Product.id)
        .where(Product.seller_id == user.id)
    )
    count_q = (
        select(func.count(Product.id))
        .outerjoin(stock_sq, stock_sq.c.pid == Product.id)
        .where(Product.seller_id == user.id)
    )
    filters = []
    if status:
        if status not in PRODUCT_STATUSES:
            _bad_request("invalid_status")
        filters.append(Product.status == status)
    if category_id:
        filters.append(Product.category_id == category_id)
    if q:
        name_sq = (
            select(ProductTranslation.product_id)
            .where(
                ProductTranslation.locale == "en",
                ProductTranslation.name.ilike(f"%{q}%"),
            )
            .scalar_subquery()
        )
        filters.append(
            (Product.slug.ilike(f"%{q}%")) | (Product.id.in_(name_sq))
        )
    total_col = func.coalesce(stock_sq.c.total, 0)
    if inventory == "out_of_stock":
        filters.append(total_col == 0)
    elif inventory == "low_stock":
        filters.append((total_col > 0) & (total_col <= LOW_STOCK_THRESHOLD))
    elif inventory == "in_stock":
        filters.append(total_col > LOW_STOCK_THRESHOLD)
    elif inventory:
        _bad_request("invalid_inventory_filter")
    for f in filters:
        base = base.where(f)
        count_q = count_q.where(f)

    total = await session.scalar(count_q)
    rows = (
        await session.execute(
            base.order_by(Product.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    product_ids = [r[0].id for r in rows]
    name_map: dict = {}
    if product_ids:
        names = (
            await session.execute(
                select(ProductTranslation).where(
                    ProductTranslation.product_id.in_(product_ids),
                    ProductTranslation.locale.in_([locale, "en"]),
                )
            )
        ).scalars().all()
        for t in names:
            name_map.setdefault(t.product_id, {})[t.locale] = t.name
    items = []
    for product, stock_total, variant_count in rows:
        names = name_map.get(product.id, {})
        items.append(
            {
                "id": product.id,
                "slug": product.slug,
                "name": names.get(locale) or names.get("en") or product.slug,
                "status": product.status,
                "base_price": product.base_price,
                "category_id": product.category_id,
                "variant_count": int(variant_count),
                "total_stock": int(stock_total),
                "stock_state": _stock_state(int(stock_total)),
            }
        )
    return {"items": items, "total": int(total or 0), "page": page, "page_size": page_size}


@router.post("/products", status_code=201)
async def create_product(
    payload: ProductCreateIn,
    user: User = Depends(require_seller),
    session: AsyncSession = Depends(get_session),
):
    _validate_translations(payload.translations, require_en=True)
    _validate_media(payload.media)
    if payload.status not in PRODUCT_STATUSES:
        _bad_request("invalid_status")
    await _validate_category(session, payload.category_id)
    await _check_skus(session, [v.sku for v in payload.variants])

    product = Product(
        seller_id=user.id,  # ownership from authenticated identity only
        category_id=payload.category_id,
        product_type=payload.product_type,
        slug=f"{_slugify(payload.translations['en'].name)}-{uuid.uuid4().hex[:6]}",
        brand=payload.brand,
        base_price=payload.base_price,
        compare_at_price=payload.compare_at_price,
        status=payload.status,
        attributes=payload.attributes,
        tags=payload.tags,
        media=payload.media,
    )
    session.add(product)
    await session.flush()
    for locale, tr in payload.translations.items():
        session.add(
            ProductTranslation(
                product_id=product.id,
                locale=locale,
                name=tr.name,
                short_description=tr.short_description,
                description=tr.description,
            )
        )
    for v in payload.variants:
        session.add(
            ProductVariant(
                product_id=product.id,
                sku=v.sku,
                option_values=v.option_values,
                stock_quantity=v.stock_quantity,
                price_override=v.price_override,
                sale_price_override=v.sale_price_override,
                image_url=v.image_url,
                is_active=v.is_active,
            )
        )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail={"error": "sku_exists"})
    return await _product_payload(session, product)


@router.get("/products/{product_id}")
async def get_product(
    product_id: str,
    user: User = Depends(require_seller),
    session: AsyncSession = Depends(get_session),
):
    product = await _own_product(session, product_id, user.id)
    return await _product_payload(session, product)


@router.patch("/products/{product_id}")
async def update_product(
    product_id: str,
    payload: ProductUpdateIn,
    user: User = Depends(require_seller),
    session: AsyncSession = Depends(get_session),
):
    product = await _own_product(session, product_id, user.id)
    data = payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in PRODUCT_STATUSES:
        _bad_request("invalid_status")
    if "category_id" in data:
        await _validate_category(session, data["category_id"])
    if "media" in data:
        _validate_media(data["media"] or [])
    if "translations" in data and data["translations"] is not None:
        translations = payload.translations or {}
        _validate_translations(translations, require_en=False)
        existing = {
            t.locale: t
            for t in (
                await session.execute(
                    select(ProductTranslation).where(
                        ProductTranslation.product_id == product.id
                    )
                )
            ).scalars().all()
        }
        for locale, tr in translations.items():
            if locale in existing:
                row = existing[locale]
                row.name = tr.name
                row.short_description = tr.short_description
                row.description = tr.description
            else:
                session.add(
                    ProductTranslation(
                        product_id=product.id,
                        locale=locale,
                        name=tr.name,
                        short_description=tr.short_description,
                        description=tr.description,
                    )
                )
    for field in (
        "category_id", "product_type", "brand", "base_price",
        "compare_at_price", "status", "attributes", "tags", "media",
    ):
        if field in data:
            setattr(product, field, data[field])
    await session.commit()
    return await _product_payload(session, product)


@router.post("/products/{product_id}/variants", status_code=201)
async def create_variant(
    product_id: str,
    payload: VariantIn,
    user: User = Depends(require_seller),
    session: AsyncSession = Depends(get_session),
):
    product = await _own_product(session, product_id, user.id)
    await _check_skus(session, [payload.sku])
    variant = ProductVariant(
        product_id=product.id,
        sku=payload.sku,
        option_values=payload.option_values,
        stock_quantity=payload.stock_quantity,
        price_override=payload.price_override,
        sale_price_override=payload.sale_price_override,
        image_url=payload.image_url,
        is_active=payload.is_active,
    )
    session.add(variant)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail={"error": "sku_exists", "skus": [payload.sku]})
    return await _product_payload(session, product)


@router.patch("/variants/{variant_id}")
async def update_variant(
    variant_id: str,
    payload: VariantUpdateIn,
    user: User = Depends(require_seller),
    session: AsyncSession = Depends(get_session),
):
    variant = await _own_variant(session, variant_id, user.id)
    data = payload.model_dump(exclude_unset=True)
    if "sku" in data and data["sku"] != variant.sku:
        await _check_skus(session, [data["sku"]], exclude_variant_id=variant.id)
    for field in ("sku", "option_values", "price_override", "sale_price_override", "image_url", "is_active"):
        if field in data:
            setattr(variant, field, data[field])
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail={"error": "sku_exists"})
    return await _product_payload(session, await _own_product(session, variant.product_id, user.id))


@router.patch("/variants/{variant_id}/inventory")
async def update_inventory(
    variant_id: str,
    payload: InventoryIn,
    user: User = Depends(require_seller),
    session: AsyncSession = Depends(get_session),
):
    variant = await session.scalar(
        select(ProductVariant)
        .join(Product, ProductVariant.product_id == Product.id)
        .where(ProductVariant.id == variant_id, Product.seller_id == user.id)
        .with_for_update()
    )
    if not variant:
        raise HTTPException(status_code=404, detail="variant_not_found")
    reserved = await _reserved_quantities(session, [variant.id])
    active_reserved = reserved.get(variant.id, 0)
    if payload.stock_quantity < active_reserved:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "below_active_reservations",
                "active_reservations": active_reserved,
                "requested": payload.stock_quantity,
            },
        )
    variant.stock_quantity = payload.stock_quantity
    await session.commit()
    return {
        "variant_id": variant.id,
        "stock_quantity": variant.stock_quantity,
        "active_reserved": active_reserved,
        "available": variant.stock_quantity - active_reserved,
        "stock_state": _stock_state(variant.stock_quantity),
    }


# ------------------------------- orders -----------------------------------


async def _seller_items_agg(session: AsyncSession, order_ids: list[str], seller_id: str) -> dict:
    if not order_ids:
        return {}
    rows = (
        await session.execute(
            select(
                OrderItem.order_id,
                func.count(OrderItem.id),
                func.coalesce(func.sum(OrderItem.line_total), 0),
            )
            .where(OrderItem.order_id.in_(order_ids), OrderItem.seller_id == seller_id)
            .group_by(OrderItem.order_id)
        )
    ).all()
    return {oid: {"item_count": int(c), "seller_subtotal": int(t)} for oid, c, t in rows}


@router.get("/orders")
async def list_seller_orders(
    user: User = Depends(require_seller),
    session: AsyncSession = Depends(get_session),
    status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
):
    base = (
        select(SellerOrderFulfillment, Order)
        .join(Order, SellerOrderFulfillment.order_id == Order.id)
        .where(SellerOrderFulfillment.seller_id == user.id)
    )
    count_q = (
        select(func.count(SellerOrderFulfillment.id))
        .where(SellerOrderFulfillment.seller_id == user.id)
    )
    if status:
        if status not in FULFILLMENT_STATUSES:
            _bad_request("invalid_status")
        base = base.where(SellerOrderFulfillment.status == status)
        count_q = count_q.where(SellerOrderFulfillment.status == status)
    total = await session.scalar(count_q)
    rows = (
        await session.execute(
            base.order_by(Order.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    agg = await _seller_items_agg(session, [o.id for _, o in rows], user.id)
    items = []
    for fulfillment, order in rows:
        a = agg.get(order.id, {"item_count": 0, "seller_subtotal": 0})
        addr = order.shipping_address or {}
        items.append(
            {
                "order_number": order.order_number,
                "created_at": order.created_at,
                "payment_state": order.payment_state,
                "order_status": order.status,
                "fulfillment_status": fulfillment.status,
                "item_count": a["item_count"],
                "seller_subtotal": a["seller_subtotal"],
                "currency": order.currency,
                "recipient": addr.get("recipient_name"),
                "destination": ", ".join(
                    x for x in [addr.get("city"), addr.get("country_code")] if x
                ),
            }
        )
    return {"items": items, "total": int(total or 0), "page": page, "page_size": page_size}


@router.get("/orders/{order_number}")
async def get_seller_order(
    order_number: str,
    user: User = Depends(require_seller),
    session: AsyncSession = Depends(get_session),
):
    row = (
        await session.execute(
            select(SellerOrderFulfillment, Order)
            .join(Order, SellerOrderFulfillment.order_id == Order.id)
            .where(
                Order.order_number == order_number,
                SellerOrderFulfillment.seller_id == user.id,
            )
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="order_not_found")
    fulfillment, order = row
    items = (
        await session.execute(
            select(OrderItem)
            .where(OrderItem.order_id == order.id, OrderItem.seller_id == user.id)
            .order_by(OrderItem.id)
        )
    ).scalars().all()
    addr = order.shipping_address or {}
    return {
        "order_number": order.order_number,
        "created_at": order.created_at,
        "payment_state": order.payment_state,
        "order_status": order.status,
        "currency": order.currency,
        "fulfillment": {
            "status": fulfillment.status,
            "tracking_number": fulfillment.tracking_number,
            "shipping_carrier": fulfillment.shipping_carrier,
            "shipped_at": fulfillment.shipped_at,
            "delivered_at": fulfillment.delivered_at,
        },
        # fulfillment-necessary customer data only (no email/account fields)
        "customer": {
            "recipient_name": addr.get("recipient_name"),
            "phone": addr.get("phone"),
            "address_line_1": addr.get("address_line_1"),
            "address_line_2": addr.get("address_line_2"),
            "city": addr.get("city"),
            "state_province": addr.get("state_province"),
            "postal_code": addr.get("postal_code"),
            "country_code": addr.get("country_code"),
        },
        "items": [
            {
                "product_name": i.product_name,
                "sku": i.sku,
                "option_values": i.option_values or {},
                "image_url": i.image_url,
                "unit_price": i.unit_price,
                "quantity": i.quantity,
                "line_total": i.line_total,
                "seller_id": i.seller_id,
            }
            for i in items
        ],
        "item_count": len(items),
        "seller_subtotal": sum(i.line_total for i in items),
    }


@router.patch("/orders/{order_number}/fulfillment")
async def update_fulfillment(
    order_number: str,
    payload: FulfillmentIn,
    user: User = Depends(require_seller),
    session: AsyncSession = Depends(get_session),
):
    row = (
        await session.execute(
            select(SellerOrderFulfillment, Order)
            .join(Order, SellerOrderFulfillment.order_id == Order.id)
            .where(
                Order.order_number == order_number,
                SellerOrderFulfillment.seller_id == user.id,
            )
            .with_for_update()
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="order_not_found")
    fulfillment, order = row

    target = payload.status
    if target not in FULFILLMENT_STATUSES:
        _bad_request("invalid_status")
    if target not in FULFILLMENT_TRANSITIONS.get(fulfillment.status, set()):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_transition",
                "current": fulfillment.status,
                "requested": target,
                "allowed": sorted(FULFILLMENT_TRANSITIONS.get(fulfillment.status, set())),
            },
        )
    # M7.1 reconciliation architecture is authoritative: only normally-paid
    # orders are fulfillable. pending_payment/payment_review/cancelled block.
    if order.payment_state != "paid":
        raise HTTPException(
            status_code=409,
            detail={"error": "payment_not_eligible", "payment_state": order.payment_state},
        )
    for value in (payload.tracking_number, payload.shipping_carrier):
        if value and _UNSAFE_TEXT.search(value):
            _bad_request("invalid_tracking")

    now = _now()
    fulfillment.status = target
    if payload.tracking_number is not None:
        fulfillment.tracking_number = payload.tracking_number
    if payload.shipping_carrier is not None:
        fulfillment.shipping_carrier = payload.shipping_carrier
    if target == "shipped":
        fulfillment.shipped_at = now
    if target == "delivered":
        fulfillment.delivered_at = now

    # derive global order status safely from ALL sellers' fulfillments
    all_rows = (
        await session.execute(
            select(SellerOrderFulfillment.status).where(
                SellerOrderFulfillment.order_id == order.id
            )
        )
    ).scalars().all()
    statuses = set(all_rows) | {target}
    if order.status in ("paid", "processing", "shipped"):
        if statuses == {"delivered"}:
            order.status = "delivered"
        elif statuses <= {"shipped", "delivered"}:
            order.status = "shipped"
        elif statuses & {"processing", "shipped", "delivered"}:
            order.status = "processing"

    await session.commit()
    return {
        "order_number": order.order_number,
        "fulfillment_status": fulfillment.status,
        "tracking_number": fulfillment.tracking_number,
        "shipping_carrier": fulfillment.shipping_carrier,
        "order_status": order.status,
    }


# ------------------------------- profile ----------------------------------


@router.get("/profile")
async def get_profile(
    user: User = Depends(require_seller),
    session: AsyncSession = Depends(get_session),
):
    profile = await session.scalar(
        select(SellerProfile).where(SellerProfile.user_id == user.id)
    )
    if not profile:
        raise HTTPException(status_code=404, detail="profile_not_found")
    return {
        "store_name": profile.store_name,
        "slug": profile.slug,
        "description": profile.description,
        "contact_phone": profile.contact_phone,
        "is_active": profile.is_active,
        "email": user.email,
        "created_at": profile.created_at,
    }


@router.patch("/profile")
async def update_profile(
    payload: ProfileIn,
    user: User = Depends(require_seller),
    session: AsyncSession = Depends(get_session),
):
    profile = await session.scalar(
        select(SellerProfile).where(SellerProfile.user_id == user.id)
    )
    if not profile:
        raise HTTPException(status_code=404, detail="profile_not_found")
    data = payload.model_dump(exclude_unset=True)
    for field in ("store_name", "description", "contact_phone"):
        if field in data:
            setattr(profile, field, data[field])
    await session.commit()
    return {
        "store_name": profile.store_name,
        "slug": profile.slug,
        "description": profile.description,
        "contact_phone": profile.contact_phone,
        "is_active": profile.is_active,
        "email": user.email,
        "created_at": profile.created_at,
    }
