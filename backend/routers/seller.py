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
from cms.service import media_url
from db.models import (
    Category,
    CmsMediaAsset,
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
from product_sizes import variants_have_required_size
from taxonomy import active_taxonomy_chain, get_root_category

router = APIRouter(prefix="/api/v1/seller", tags=["seller"])

require_seller = require_roles("seller")

LOCALES = {"id", "en", "uz", "ru"}
PRODUCT_STATUSES = {"draft", "active", "inactive"}
PRODUCT_TYPES = {"general", "apparel", "hijab", "skincare", "batik", "parfum"}
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


def _validate_product_sizes(department: Optional[str], variants: list[dict]) -> None:
    if not variants_have_required_size(department, variants):
        _bad_request("size_required_for_department", {"department": department})


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
    media_id: Optional[str] = Field(default=None, max_length=40)
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
    expected_revision: Optional[int] = Field(default=None, ge=1)
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
    expected_revision: Optional[int] = Field(default=None, ge=1)
    sku: Optional[str] = Field(default=None, min_length=2, max_length=80)
    option_values: Optional[dict] = None
    price_override: Optional[int] = Field(default=None, ge=0)
    sale_price_override: Optional[int] = Field(default=None, ge=0)
    media_id: Optional[str] = Field(default=None, max_length=40)
    image_url: Optional[str] = Field(default=None, max_length=500)
    is_active: Optional[bool] = None


class InventoryIn(BaseModel):
    expected_revision: Optional[int] = Field(default=None, ge=1)
    stock_quantity: int = Field(ge=0)


class VariantCreateWithRevisionIn(VariantIn):
    expected_revision: Optional[int] = Field(default=None, ge=1)


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
    for locale, translation in translations.items():
        for field in ("name", "short_description", "description"):
            value = (
                translation.get(field)
                if isinstance(translation, dict)
                else getattr(translation, field, None)
            )
            if value is not None and not isinstance(value, str):
                _bad_request("invalid_translation", {"locale": locale, "field": field})
            if field == "name" and (not isinstance(value, str) or not value.strip()):
                _bad_request("translation_name_required", {"locale": locale})
            if value and _UNSAFE_TEXT.search(value):
                _bad_request("unsafe_text", {"locale": locale, "field": field})


def _validate_price_order(base_price: int, compare_at_price: Optional[int]) -> None:
    if compare_at_price is not None and compare_at_price < base_price:
        _bad_request("compare_price_below_base")


def _validate_product_type(product_type: str) -> None:
    if product_type not in PRODUCT_TYPES:
        _bad_request("invalid_product_type", {"allowed": sorted(PRODUCT_TYPES)})


def _normalize_option_values(values: dict) -> dict[str, str]:
    """Keep variant options JSON-safe, scalar, and stable for filtering."""

    if not isinstance(values, dict) or len(values) > 20:
        _bad_request("invalid_option_values")
    normalized: dict[str, str] = {}
    for raw_key, raw_value in values.items():
        if not isinstance(raw_key, str):
            _bad_request("invalid_option_values")
        key = raw_key.strip()
        if not key or len(key) > 40 or key in normalized:
            _bad_request("invalid_option_values")
        if raw_value is None or isinstance(raw_value, (dict, list, tuple, set)):
            _bad_request("invalid_option_values", {"key": key})
        if not isinstance(raw_value, (str, int, float, bool)):
            _bad_request("invalid_option_values", {"key": key})
        value = str(raw_value).strip()
        if not value or len(value) > 120:
            _bad_request("invalid_option_values", {"key": key})
        normalized[key] = value
    return normalized


def _normalize_sku(sku: str) -> str:
    """Trim SKU input and reject values that cannot be safely identified."""

    normalized = sku.strip()
    if len(normalized) < 2 or any(ord(char) < 33 for char in normalized):
        _bad_request("invalid_sku")
    return normalized


def _validate_variant_prices(
    price_override: Optional[int],
    sale_price_override: Optional[int],
    base_price: Optional[int] = None,
) -> None:
    regular_price = price_override if price_override is not None else base_price
    if sale_price_override is not None and regular_price is not None and sale_price_override >= regular_price:
        _bad_request("sale_price_not_below_regular")


def _validate_active_product_payload(status: str, translations: dict, variants) -> None:
    """Reject a product that would be published without a usable storefront row."""

    if status != "active":
        return
    english = translations.get("en") if isinstance(translations, dict) else None
    english_name = (
        english.get("name") if isinstance(english, dict) else getattr(english, "name", None)
    )
    if not isinstance(english_name, str) or not english_name.strip():
        _bad_request("translation_en_required")
    if not any(
        bool(
            variant.get("is_active", False)
            if isinstance(variant, dict)
            else getattr(variant, "is_active", False)
        )
        for variant in variants
    ):
        _bad_request("active_product_requires_variant")


async def _validate_existing_variant_prices(
    session: AsyncSession, product_id: str, base_price: int
) -> None:
    """Keep a product-wide base-price edit from invalidating variant prices."""

    rows = (
        await session.execute(
            select(ProductVariant.price_override, ProductVariant.sale_price_override)
            .where(ProductVariant.product_id == product_id)
        )
    ).all()
    for price_override, sale_price_override in rows:
        _validate_variant_prices(price_override, sale_price_override, base_price)


async def _ensure_existing_product_is_publishable(
    session: AsyncSession,
    product_id: str,
    status: str,
    translations: Optional[dict] = None,
) -> None:
    """Validate activation when the endpoint is only changing product fields."""

    if status != "active":
        return
    if translations is None or "en" not in translations:
        english_name = await session.scalar(
            select(ProductTranslation.name).where(
                ProductTranslation.product_id == product_id,
                ProductTranslation.locale == "en",
            )
        )
        if not isinstance(english_name, str) or not english_name.strip():
            _bad_request("translation_en_required")
    else:
        english = translations.get("en")
        english_name = (
            english.get("name")
            if isinstance(english, dict)
            else getattr(english, "name", None)
        )
        if not isinstance(english_name, str) or not english_name.strip():
            _bad_request("translation_en_required")
    has_active_variant = await session.scalar(
        select(ProductVariant.id)
        .where(
            ProductVariant.product_id == product_id,
            ProductVariant.is_active.is_(True),
        )
        .limit(1)
    )
    if not has_active_variant:
        _bad_request("active_product_requires_variant")


async def _check_skus(
    session: AsyncSession,
    skus: list[str],
    exclude_variant_id: Optional[str] = None,
    exclude_variant_ids: Optional[set[str]] = None,
) -> None:
    folded = [sku.casefold() for sku in skus]
    dupes = {skus[index] for index, value in enumerate(folded) if folded.count(value) > 1}
    if dupes:
        raise HTTPException(status_code=409, detail={"error": "sku_duplicate_in_payload", "skus": sorted(dupes)})
    # The database's legacy unique constraint is case-sensitive. Serialize
    # the case-insensitive application check so two concurrent admin/seller
    # writes cannot both pass the read and create SKU aliases such as
    # ``MC-001`` and ``mc-001``.
    for value in sorted(set(folded)):
        await session.execute(
            select(func.pg_advisory_xact_lock(func.hashtext(f"sku:{value}")))
        )
    query = select(ProductVariant.sku).where(func.lower(ProductVariant.sku).in_(folded))
    excluded = set(exclude_variant_ids or set())
    if exclude_variant_id:
        excluded.add(exclude_variant_id)
    if excluded:
        query = query.where(~ProductVariant.id.in_(excluded))
    taken = (await session.execute(query)).scalars().all()
    if taken:
        raise HTTPException(status_code=409, detail={"error": "sku_exists", "skus": sorted(taken)})


def _validate_local_media_url(url: Optional[str]) -> None:
    """Accept legacy/internal media paths, never arbitrary remote images."""

    if url in (None, ""):
        return
    if (
        not isinstance(url, str)
        or len(url) > 500
        or not url.startswith("/")
        or url.startswith("//")
    ):
        _bad_request("invalid_media_url")


async def _resolve_media_reference(session: AsyncSession, media_id: Optional[str]) -> Optional[str]:
    if not media_id:
        return None
    # Serialize media references with CMS deletion so a successful product
    # mutation can never commit a pointer to an asset deleted concurrently.
    asset = await session.scalar(
        select(CmsMediaAsset).where(CmsMediaAsset.id == media_id).with_for_update()
    )
    if not asset:
        _bad_request("invalid_media")
    return await media_url(session, asset)


async def _normalize_media(session: AsyncSession, media: list[dict]) -> list[dict]:
    _validate_media(media)
    normalized = []
    for raw in media:
        item = dict(raw)
        if item.get("media_id"):
            item["url"] = await _resolve_media_reference(session, item["media_id"])
        normalized.append(item)
    return normalized


async def _validate_category(
    session: AsyncSession, category_id: str, product_type: Optional[str] = None
) -> None:
    category = await session.scalar(
        select(Category)
        .where(
            Category.id == category_id,
            Category.is_active == True,
            Category.kind == "category",
        )
        .with_for_update()
    )
    if not category:
        _bad_request("invalid_category")
    # A leaf is public only when every ancestor is active and the chain ends
    # at a department. This keeps legacy/malformed rows from becoming a way
    # to publish a product below an inactive or orphaned taxonomy node.
    if not await active_taxonomy_chain(session, category, lock=True):
        _bad_request("invalid_category")
    child_count = await session.scalar(
        select(func.count(Category.id)).where(Category.parent_id == category.id)
    )
    if child_count:
        _bad_request("category_not_leaf")
    if product_type in {"batik", "parfum"} or category.department in {"batik", "parfum"}:
        root = await get_root_category(session, category, lock=True)
        if not root or root.slug != product_type:
            _bad_request(
                "product_type_category_mismatch",
                {"product_type": product_type, "department": root.slug if root else category.department},
            )


def _validate_media(media: list[dict]) -> None:
    if len(media) > 8:
        _bad_request("too_many_media")
    for m in media:
        if not isinstance(m, dict):
            _bad_request("invalid_media")
        if m.get("media_id"):
            if not isinstance(m["media_id"], str) or not m["media_id"].strip():
                _bad_request("invalid_media")
            continue
        url = (m or {}).get("url", "")
        _validate_local_media_url(url)
        if not url:
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
        "revision": product.revision,
        "attributes": product.attributes or {},
        "tags": product.tags or [],
        "media": product.media or [],
        "translations": _translation_map(translations),
        "is_demo": product.is_demo,
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
                "media_id": v.media_id,
                "image_url": v.image_url,
                "is_active": v.is_active,
                "stock_state": _stock_state(v.stock_quantity),
            }
            for v in variants
        ],
    }


def _advance_product_revision(product: Product) -> int:
    product.revision = int(product.revision or 1) + 1
    return product.revision


async def _ensure_product_revision(
    session: AsyncSession, product: Product, expected_revision: Optional[int]
) -> None:
    if expected_revision is None:
        raise HTTPException(status_code=428, detail={"error": "revision_required"})
    if int(expected_revision) != int(product.revision or 1):
        current = await _product_payload(session, product)
        raise HTTPException(
            status_code=409,
            detail={"error": "product_changed", "current": current},
        )


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
                "revision": product.revision,
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
    _validate_product_type(payload.product_type)
    normalized_media = await _normalize_media(session, payload.media)
    if payload.status not in PRODUCT_STATUSES:
        _bad_request("invalid_status")
    _validate_active_product_payload(payload.status, payload.translations, payload.variants)
    await _validate_category(session, payload.category_id, payload.product_type)
    _validate_price_order(payload.base_price, payload.compare_at_price)
    normalized_skus = [_normalize_sku(variant.sku) for variant in payload.variants]
    normalized_options = [
        _normalize_option_values(variant.option_values) for variant in payload.variants
    ]
    category = await session.get(Category, payload.category_id)
    _validate_product_sizes(
        category.department if category else None, normalized_options
    )
    for variant in payload.variants:
        _validate_variant_prices(
            variant.price_override, variant.sale_price_override, payload.base_price
        )
    await _check_skus(session, normalized_skus)

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
        media=normalized_media,
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
    for v, sku, option_values in zip(payload.variants, normalized_skus, normalized_options):
        variant_image_url = (
            await _resolve_media_reference(session, v.media_id)
            if v.media_id
            else v.image_url
        )
        if not v.media_id:
            _validate_local_media_url(variant_image_url)
        session.add(
            ProductVariant(
                product_id=product.id,
                sku=sku,
                option_values=option_values,
                stock_quantity=v.stock_quantity,
                price_override=v.price_override,
                sale_price_override=v.sale_price_override,
                media_id=v.media_id,
                image_url=variant_image_url,
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
    product = await session.scalar(
        select(Product)
        .where(Product.id == product_id, Product.seller_id == user.id)
        .with_for_update()
    )
    if not product:
        raise HTTPException(status_code=404, detail="product_not_found")
    await _ensure_product_revision(session, product, payload.expected_revision)
    data = payload.model_dump(exclude_unset=True, exclude={"expected_revision"})
    if "status" in data and data["status"] not in PRODUCT_STATUSES:
        _bad_request("invalid_status")
    if "product_type" in data:
        _validate_product_type(data["product_type"])
    if (
        "category_id" in data
        or "product_type" in data
        or data.get("status", product.status) == "active"
    ):
        await _validate_category(
            session,
            data.get("category_id", product.category_id),
            data.get("product_type", product.product_type),
        )
    if data.get("category_id", product.category_id) != product.category_id:
        target_category = await session.get(Category, data["category_id"])
        current_options = (
            await session.execute(
                select(ProductVariant.option_values).where(
                    ProductVariant.product_id == product.id
                )
            )
        ).scalars().all()
        _validate_product_sizes(
            target_category.department if target_category else None,
            [options or {} for options in current_options],
        )
    if "media" in data:
        data["media"] = await _normalize_media(session, data["media"] or [])
    _validate_price_order(
        data.get("base_price", product.base_price),
        data.get("compare_at_price", product.compare_at_price),
    )
    await _validate_existing_variant_prices(
        session, product.id, data.get("base_price", product.base_price)
    )
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
    await _ensure_existing_product_is_publishable(
        session,
        product.id,
        data.get("status", product.status),
        data.get("translations") if "translations" in data else None,
    )
    for field in (
        "category_id", "product_type", "brand", "base_price",
        "compare_at_price", "status", "attributes", "tags", "media",
    ):
        if field in data:
            setattr(product, field, data[field])
    _advance_product_revision(product)
    await session.commit()
    return await _product_payload(session, product)


@router.post("/products/{product_id}/variants", status_code=201)
async def create_variant(
    product_id: str,
    payload: VariantCreateWithRevisionIn,
    user: User = Depends(require_seller),
    session: AsyncSession = Depends(get_session),
):
    product = await session.scalar(
        select(Product)
        .where(Product.id == product_id, Product.seller_id == user.id)
        .with_for_update()
    )
    if not product:
        raise HTTPException(status_code=404, detail="product_not_found")
    await _ensure_product_revision(session, product, payload.expected_revision)
    _validate_variant_prices(
        payload.price_override, payload.sale_price_override, product.base_price
    )
    sku = _normalize_sku(payload.sku)
    option_values = _normalize_option_values(payload.option_values)
    category = await session.get(Category, product.category_id)
    _validate_product_sizes(
        category.department if category else None, [option_values]
    )
    await _check_skus(session, [sku])
    variant_image_url = (
        await _resolve_media_reference(session, payload.media_id)
        if payload.media_id
        else payload.image_url
    )
    if not payload.media_id:
        _validate_local_media_url(variant_image_url)
    variant = ProductVariant(
        product_id=product.id,
        sku=sku,
        option_values=option_values,
        stock_quantity=payload.stock_quantity,
        price_override=payload.price_override,
        sale_price_override=payload.sale_price_override,
        media_id=payload.media_id,
        image_url=variant_image_url,
        is_active=payload.is_active,
    )
    session.add(variant)
    _advance_product_revision(product)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail={"error": "sku_exists", "skus": [sku]})
    return await _product_payload(session, product)


@router.patch("/variants/{variant_id}")
async def update_variant(
    variant_id: str,
    payload: VariantUpdateIn,
    user: User = Depends(require_seller),
    session: AsyncSession = Depends(get_session),
):
    variant_product_id = await session.scalar(
        select(ProductVariant.product_id)
        .join(Product, ProductVariant.product_id == Product.id)
        .where(ProductVariant.id == variant_id, Product.seller_id == user.id)
    )
    if not variant_product_id:
        raise HTTPException(status_code=404, detail="variant_not_found")
    # Use the same product -> variant order as product-editor and inventory
    # mutations so concurrent edits cannot deadlock.
    product = await session.scalar(
        select(Product)
        .where(Product.id == variant_product_id, Product.seller_id == user.id)
        .with_for_update()
    )
    variant = await session.scalar(
        select(ProductVariant)
        .where(
            ProductVariant.id == variant_id,
            ProductVariant.product_id == variant_product_id,
        )
        .with_for_update()
    )
    if not product or not variant:
        raise HTTPException(status_code=404, detail="variant_not_found")
    await _ensure_product_revision(session, product, payload.expected_revision)
    data = payload.model_dump(exclude_unset=True, exclude={"expected_revision"})
    if "sku" in data:
        data["sku"] = _normalize_sku(data["sku"])
        if data["sku"] != variant.sku:
            await _check_skus(session, [data["sku"]], exclude_variant_id=variant.id)
    _validate_variant_prices(
        data.get("price_override", variant.price_override),
        data.get("sale_price_override", variant.sale_price_override),
        product.base_price if product else None,
    )
    if "media_id" in data:
        data["image_url"] = await _resolve_media_reference(session, data["media_id"])
    elif "image_url" in data:
        _validate_local_media_url(data["image_url"])
    if "option_values" in data:
        data["option_values"] = _normalize_option_values(data["option_values"])
        if data["option_values"] != (variant.option_values or {}):
            category = await session.get(Category, product.category_id)
            _validate_product_sizes(
                category.department if category else None,
                [data["option_values"]],
            )
    for field in ("sku", "option_values", "price_override", "sale_price_override", "media_id", "image_url", "is_active"):
        if field in data:
            setattr(variant, field, data[field])
    _advance_product_revision(product)
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
    variant_product_id = await session.scalar(
        select(ProductVariant.product_id)
        .join(Product, ProductVariant.product_id == Product.id)
        .where(ProductVariant.id == variant_id, Product.seller_id == user.id)
    )
    if not variant_product_id:
        raise HTTPException(status_code=404, detail="variant_not_found")
    product = await session.scalar(
        select(Product)
        .where(Product.id == variant_product_id, Product.seller_id == user.id)
        .with_for_update()
    )
    variant = await session.scalar(
        select(ProductVariant)
        .where(
            ProductVariant.id == variant_id,
            ProductVariant.product_id == variant_product_id,
        )
        .with_for_update()
    )
    if not product or not variant:
        raise HTTPException(status_code=404, detail="variant_not_found")
    await _ensure_product_revision(session, product, payload.expected_revision)
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
    _advance_product_revision(product)
    await session.commit()
    return {
        "variant_id": variant.id,
        "revision": product.revision,
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
