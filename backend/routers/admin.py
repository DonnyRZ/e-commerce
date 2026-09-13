"""Admin Core API — single-operator store management.

Role: admin only (customers and legacy seller accounts are blocked).
Reuses the seller-router validation helpers but without seller scoping —
the admin operates ALL catalog content as the single store owner.
Order fulfillment is order-level (single-vendor), gated on payment_state.
No payment secrets are ever exposed; payment events are sanitized.
"""

from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth import csrf_protect, require_roles
from cms.service import audit, media_url
from config import (
    BASE_CURRENCY,
    CHECKOUT_ENABLED,
    INVENTORY_RESERVATION_TTL_MINUTES,
    SHIPPING_PROVIDER,
)
from db.models import (
    Category,
    CategoryTranslation,
    CmsMediaAsset,
    Order,
    OrderItem,
    Payment,
    PaymentEvent,
    Product,
    ProductTranslation,
    ProductVariant,
    SellerOrderFulfillment,
    User,
)
from db.session import get_session
from routers.seller import (
    InventoryIn,
    ProductCreateIn,
    ProductUpdateIn,
    VariantIn,
    VariantUpdateIn,
    _bad_request,
    _check_skus,
    _product_payload,
    _stock_state,
    _validate_category,
    _validate_local_media_url,
    _validate_media,
    _validate_price_order,
    _validate_product_type,
    _validate_variant_prices,
    _validate_translations,
)
from checkout.service import _reserved_quantities
from taxonomy import TAXONOMY_KINDS, descendant_ids_select, get_root_category

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

require_admin = require_roles("admin")

ORDER_TRANSITIONS = {"paid": "processing", "processing": "shipped", "shipped": "delivered"}
LOCALES = ("id", "en", "uz", "ru")


def _now():
    return datetime.now(timezone.utc)


async def _store_owner_id(session: AsyncSession, admin_id: str) -> str:
    """Single-vendor: products are owned by the internal store account."""
    owner = await session.scalar(
        select(User).where(User.email == "official@muslimahcantik.id")
    )
    return owner.id if owner else admin_id


async def _resolve_media_url(session: AsyncSession, media_id: Optional[str]) -> Optional[str]:
    """Validate a CMS asset reference and resolve its local browser URL."""
    if not media_id:
        return None
    asset = await session.get(CmsMediaAsset, media_id)
    if not asset:
        _bad_request("invalid_media")
    return await media_url(session, asset)


async def _normalize_product_media(session: AsyncSession, media: list[dict]) -> list[dict]:
    """Make media_id authoritative while retaining legacy URL compatibility."""
    _validate_media(media)
    normalized = []
    for raw in media:
        item = dict(raw or {})
        if item.get("media_id"):
            item["url"] = await _resolve_media_url(session, item["media_id"])
        normalized.append(item)
    return normalized


# ------------------------------ dashboard -----------------------------------


@router.get("/dashboard")
async def admin_dashboard(
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    total_products = await session.scalar(select(func.count(Product.id)))
    active_products = await session.scalar(
        select(func.count(Product.id)).where(Product.status == "active")
    )
    variant_rows = (
        await session.execute(
            select(ProductVariant.stock_quantity).where(ProductVariant.is_active == True)
        )
    ).scalars().all()
    low_stock = sum(1 for s in variant_rows if 0 < s <= 5)
    out_of_stock = sum(1 for s in variant_rows if s == 0)

    order_counts = (
        await session.execute(select(Order.status, func.count()).group_by(Order.status))
    ).all()
    orders_by_status = {status: count for status, count in order_counts}
    review_payments = await session.scalar(
        select(func.count(Payment.id)).where(Payment.status == "reconciliation_required")
    )
    sales = await session.scalar(
        select(func.coalesce(func.sum(Order.grand_total), 0)).where(Order.payment_state == "paid")
    )
    recent = (
        await session.execute(select(Order).order_by(Order.created_at.desc()).limit(5))
    ).scalars().all()
    recent_orders = []
    for order in recent:
        count = await session.scalar(
            select(func.count(OrderItem.id)).where(OrderItem.order_id == order.id)
        )
        recent_orders.append(
            {
                "order_number": order.order_number,
                "created_at": order.created_at,
                "status": order.status,
                "payment_state": order.payment_state,
                "grand_total": order.grand_total,
                "currency": order.currency,
                "item_count": int(count or 0),
            }
        )
    return {
        "total_products": int(total_products or 0),
        "active_products": int(active_products or 0),
        "low_stock_variants": low_stock,
        "out_of_stock_variants": out_of_stock,
        "orders_by_status": orders_by_status,
        "orders_needing_action": orders_by_status.get("paid", 0) + orders_by_status.get("processing", 0),
        "payment_review_count": orders_by_status.get("payment_review", 0) + int(review_payments or 0),
        "sales_total": int(sales or 0),
        "currency": BASE_CURRENCY,
        "recent_orders": recent_orders,
    }


# ------------------------------ products -----------------------------------


@router.get("/products")
async def admin_list_products(
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    q: Optional[str] = Query(default=None, max_length=120),
    status: Optional[str] = Query(default=None),
    category_id: Optional[str] = Query(default=None),
    inventory: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
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
    base = select(
        Product, func.coalesce(stock_sq.c.total, 0), func.coalesce(stock_sq.c.variant_count, 0)
    ).outerjoin(stock_sq, stock_sq.c.pid == Product.id)
    count_q = select(func.count(Product.id)).outerjoin(
        stock_sq, stock_sq.c.pid == Product.id
    )
    filters = []
    if status:
        if status not in ("draft", "active", "inactive"):
            _bad_request("invalid_status")
        filters.append(Product.status == status)
    if category_id:
        filters.append(Product.category_id == category_id)
    if q:
        like = f"%{q}%"
        name_sq = (
            select(ProductTranslation.product_id)
            .where(ProductTranslation.locale == "en", ProductTranslation.name.ilike(like))
            .scalar_subquery()
        )
        filters.append(Product.slug.ilike(like) | Product.id.in_(name_sq) | Product.brand.ilike(like))
    total_col = func.coalesce(stock_sq.c.total, 0)
    if inventory == "out_of_stock":
        filters.append(total_col == 0)
    elif inventory == "low_stock":
        filters.append((total_col > 0) & (total_col <= 5))
    elif inventory == "in_stock":
        filters.append(total_col > 5)
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
                "is_demo": product.is_demo,
                "base_price": product.base_price,
                "category_id": product.category_id,
                "brand": product.brand,
                "variant_count": int(variant_count),
                "total_stock": int(stock_total),
                "stock_state": _stock_state(int(stock_total)),
            }
        )
    return {"items": items, "total": int(total or 0), "page": page, "page_size": page_size}


@router.post("/products", status_code=201)
async def admin_create_product(
    payload: ProductCreateIn,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    _validate_translations(payload.translations, require_en=True)
    _validate_product_type(payload.product_type)
    normalized_media = await _normalize_product_media(session, payload.media)
    if payload.status not in ("draft", "active", "inactive"):
        _bad_request("invalid_status")
    await _validate_category(session, payload.category_id, payload.product_type)
    _validate_price_order(payload.base_price, payload.compare_at_price)
    for variant in payload.variants:
        _validate_variant_prices(
            variant.price_override, variant.sale_price_override, payload.base_price
        )
    await _check_skus(session, [v.sku for v in payload.variants])
    import uuid as _uuid
    import re as _re

    slug_base = _re.sub(r"[^a-z0-9]+", "-", payload.translations["en"].name.lower()).strip("-")[:80]
    product = Product(
        seller_id=await _store_owner_id(session, user.id),
        category_id=payload.category_id,
        product_type=payload.product_type,
        slug=f"{slug_base or 'product'}-{_uuid.uuid4().hex[:6]}",
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
            ProductTranslation(product_id=product.id, locale=locale, name=tr.name,
                short_description=tr.short_description, description=tr.description)
        )
    for v in payload.variants:
        variant_image_url = await _resolve_media_url(session, v.media_id) if v.media_id else v.image_url
        if not v.media_id:
            _validate_local_media_url(variant_image_url)
        session.add(
            ProductVariant(
                product_id=product.id, sku=v.sku, option_values=v.option_values,
                stock_quantity=v.stock_quantity, price_override=v.price_override,
                sale_price_override=v.sale_price_override, media_id=v.media_id,
                image_url=variant_image_url,
                is_active=v.is_active,
            )
        )
    await audit(session, user.id, "admin.product.create", "product", product.id,
                {"slug": product.slug})
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail={"error": "sku_exists"})
    return await _product_payload(session, product)


@router.get("/products/{product_id}")
async def admin_get_product(
    product_id: str,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    product = await session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="product_not_found")
    return await _product_payload(session, product)


@router.patch("/products/{product_id}")
async def admin_update_product(
    product_id: str,
    payload: ProductUpdateIn,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    product = await session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="product_not_found")
    data = payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in ("draft", "active", "inactive"):
        _bad_request("invalid_status")
    if "product_type" in data:
        _validate_product_type(data["product_type"])
    if "category_id" in data or "product_type" in data:
        await _validate_category(
            session,
            data.get("category_id", product.category_id),
            data.get("product_type", product.product_type),
        )
    if "media" in data:
        data["media"] = await _normalize_product_media(session, data["media"] or [])
    _validate_price_order(
        data.get("base_price", product.base_price),
        data.get("compare_at_price", product.compare_at_price),
    )
    translations = data.pop("translations", None)
    if translations:
        _validate_translations(payload.translations or {}, require_en=False)
        existing = {
            t.locale: t
            for t in (
                await session.execute(
                    select(ProductTranslation).where(ProductTranslation.product_id == product.id)
                )
            ).scalars().all()
        }
        for locale, tr in (payload.translations or {}).items():
            if locale in existing:
                row = existing[locale]
                row.name = tr.name
                row.short_description = tr.short_description
                row.description = tr.description
            else:
                session.add(
                    ProductTranslation(product_id=product.id, locale=locale, name=tr.name,
                        short_description=tr.short_description, description=tr.description)
                )
    for field in ("category_id", "product_type", "brand", "base_price",
                  "compare_at_price", "status", "attributes", "tags", "media"):
        if field in data:
            setattr(product, field, data[field])
    await audit(session, user.id, "admin.product.update", "product", product.id,
                {"fields": sorted(data.keys())})
    await session.commit()
    return await _product_payload(session, product)


@router.post("/products/{product_id}/variants", status_code=201)
async def admin_create_variant(
    product_id: str,
    payload: VariantIn,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    product = await session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="product_not_found")
    await _check_skus(session, [payload.sku])
    _validate_variant_prices(
        payload.price_override, payload.sale_price_override, product.base_price
    )
    variant_image_url = await _resolve_media_url(session, payload.media_id) if payload.media_id else payload.image_url
    if not payload.media_id:
        _validate_local_media_url(variant_image_url)
    variant = ProductVariant(
        product_id=product.id, sku=payload.sku, option_values=payload.option_values,
        stock_quantity=payload.stock_quantity, price_override=payload.price_override,
        sale_price_override=payload.sale_price_override,
        media_id=payload.media_id, image_url=variant_image_url,
        is_active=payload.is_active,
    )
    session.add(variant)
    await audit(session, user.id, "admin.variant.create", "product", product.id,
                {"sku": payload.sku})
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail={"error": "sku_exists", "skus": [payload.sku]})
    return await _product_payload(session, product)


@router.patch("/variants/{variant_id}")
async def admin_update_variant(
    variant_id: str,
    payload: VariantUpdateIn,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    variant = await session.get(ProductVariant, variant_id)
    if not variant:
        raise HTTPException(status_code=404, detail="variant_not_found")
    data = payload.model_dump(exclude_unset=True)
    if "sku" in data and data["sku"] != variant.sku:
        await _check_skus(session, [data["sku"]], exclude_variant_id=variant.id)
    product = await session.get(Product, variant.product_id)
    _validate_variant_prices(
        data.get("price_override", variant.price_override),
        data.get("sale_price_override", variant.sale_price_override),
        product.base_price if product else None,
    )
    if "media_id" in data:
        data["image_url"] = await _resolve_media_url(session, data["media_id"])
    elif "image_url" in data:
        _validate_local_media_url(data["image_url"])
    for field in ("sku", "option_values", "price_override", "sale_price_override",
                  "media_id", "image_url", "is_active"):
        if field in data:
            setattr(variant, field, data[field])
    await audit(session, user.id, "admin.variant.update", "variant", variant.id,
                {"fields": sorted(data.keys())})
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail={"error": "sku_exists"})
    product = await session.get(Product, variant.product_id)
    return await _product_payload(session, product)


@router.patch("/variants/{variant_id}/inventory")
async def admin_update_inventory(
    variant_id: str,
    payload: InventoryIn,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    variant = await session.scalar(
        select(ProductVariant).where(ProductVariant.id == variant_id).with_for_update()
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
    await audit(session, user.id, "admin.inventory.update", "variant", variant.id,
                {"stock_quantity": payload.stock_quantity})
    await session.commit()
    return {
        "variant_id": variant.id,
        "stock_quantity": variant.stock_quantity,
        "active_reserved": active_reserved,
        "available": variant.stock_quantity - active_reserved,
        "stock_state": _stock_state(variant.stock_quantity),
    }


# ------------------------------ categories ---------------------------------


class CategoryTranslationIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)


class CategoryCreateIn(BaseModel):
    slug: str = Field(min_length=2, max_length=120)
    department: str = Field(min_length=1, max_length=50)
    kind: Literal["department", "group", "category"] = "category"
    parent_id: Optional[str] = Field(default=None, min_length=8, max_length=40)
    sort_order: int = Field(default=0, ge=0)
    media_id: Optional[str] = Field(default=None, max_length=40)
    image_url: Optional[str] = Field(default=None, max_length=500)
    # New taxonomy nodes are staged first; activate only after content and
    # product mapping have been reviewed.
    is_active: bool = False
    translations: dict[str, CategoryTranslationIn]


class CategoryUpdateIn(BaseModel):
    parent_id: Optional[str] = Field(default=None, min_length=8, max_length=40)
    sort_order: Optional[int] = Field(default=None, ge=0)
    media_id: Optional[str] = Field(default=None, max_length=40)
    image_url: Optional[str] = None
    is_active: Optional[bool] = None
    translations: Optional[dict[str, CategoryTranslationIn]] = None


async def _category_payload(session: AsyncSession, category: Category) -> dict:
    translations = (
        await session.execute(
            select(CategoryTranslation).where(CategoryTranslation.category_id == category.id)
        )
    ).scalars().all()
    product_count = await session.scalar(
        select(func.count(Product.id)).where(
            Product.category_id.in_(
                select(Category.id).where(
                    Category.id.in_(descendant_ids_select(category.id)),
                    Category.kind == "category",
                )
            )
        )
    )
    child_count = await session.scalar(
        select(func.count(Category.id)).where(Category.parent_id == category.id)
    )
    return {
        "id": category.id,
        "slug": category.slug,
        "department": category.department,
        "kind": category.kind,
        "parent_id": category.parent_id,
        "sort_order": category.sort_order,
        "media_id": category.media_id,
        "image_url": category.image_url,
        "is_active": category.is_active,
        "product_count": int(product_count or 0),
        "child_count": int(child_count or 0),
        "is_leaf": category.kind == "category" and not child_count,
        "translations": {
            t.locale: {"name": t.name, "description": t.description} for t in translations
        },
    }


async def _category_parent(
    session: AsyncSession,
    kind: str,
    department: str,
    requested_parent_id: Optional[str] = None,
    slug: Optional[str] = None,
    current_id: Optional[str] = None,
) -> Optional[str]:
    if kind not in TAXONOMY_KINDS:
        _bad_request("invalid_category_kind")
    if kind == "department":
        if slug != department or requested_parent_id:
            _bad_request("invalid_department_parent")
        return None

    root = await session.scalar(
        select(Category).where(
            Category.kind == "department", Category.slug == department
        )
    )
    if not root:
        _bad_request("invalid_department", {"allowed": [department]})

    parent = await session.get(Category, requested_parent_id) if requested_parent_id else root
    if not parent:
        _bad_request("invalid_category_parent")
    if current_id and parent.id == current_id:
        _bad_request("category_parent_cycle")
    if kind == "group" and parent.kind != "department":
        _bad_request("group_parent_must_be_department")
    if kind == "category" and parent.kind not in ("department", "group"):
        _bad_request("category_parent_must_be_department_or_group")
    parent_root = await get_root_category(session, parent)
    if not parent_root or parent_root.id != root.id:
        _bad_request("invalid_category_parent")

    # A malformed existing tree must not be made worse by a move.
    if current_id:
        seen = {current_id}
        cursor = parent
        while cursor.parent_id:
            if cursor.id in seen:
                _bad_request("category_parent_cycle")
            seen.add(cursor.id)
            cursor = await session.get(Category, cursor.parent_id)
            if not cursor:
                _bad_request("invalid_category_parent")
    return parent.id


@router.get("/categories")
async def admin_list_categories(
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    rows = (
        await session.execute(
            select(Category).order_by(
                case(
                    (Category.kind == "category", 0),
                    (Category.kind == "group", 1),
                    else_=2,
                ),
                Category.department,
                Category.sort_order,
                Category.slug,
            )
        )
    ).scalars().all()
    departments = (
        await session.execute(
            select(Category.slug)
            .where(Category.kind == "department")
            .order_by(Category.slug)
        )
    ).scalars().all()
    return {
        "items": [await _category_payload(session, c) for c in rows],
        "departments": [d for d in departments if d],
    }


@router.post("/categories", status_code=201)
async def admin_create_category(
    payload: CategoryCreateIn,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    import re as _re

    if not _re.match(r"^[a-z0-9][a-z0-9\-]{1,118}$", payload.slug):
        _bad_request("invalid_slug")
    unknown = set(payload.translations) - set(LOCALES)
    if unknown:
        _bad_request("invalid_locale", {"locales": sorted(unknown)})
    if "en" not in payload.translations:
        _bad_request("translation_en_required")
    parent_id = await _category_parent(
        session,
        payload.kind,
        payload.department,
        payload.parent_id,
        payload.slug,
    )
    if payload.is_active and parent_id:
        parent = await session.get(Category, parent_id)
        if parent and not parent.is_active:
            _bad_request("parent_inactive")
    if payload.media_id:
        image_url = await _resolve_media_url(session, payload.media_id)
    else:
        _validate_local_media_url(payload.image_url)
        image_url = payload.image_url
    dupe = await session.scalar(select(Category).where(Category.slug == payload.slug))
    if dupe:
        raise HTTPException(status_code=409, detail={"error": "slug_exists"})
    category = Category(
        slug=payload.slug, kind=payload.kind, department=payload.department,
        parent_id=parent_id,
        sort_order=payload.sort_order,
        media_id=payload.media_id,
        image_url=image_url,
        is_active=payload.is_active,
    )
    session.add(category)
    await session.flush()
    for locale, tr in payload.translations.items():
        session.add(
            CategoryTranslation(category_id=category.id, locale=locale,
                                name=tr.name, description=tr.description)
        )
    await audit(session, user.id, "admin.category.create", "category", category.id,
                {"slug": category.slug})
    await session.commit()
    return await _category_payload(session, category)


@router.patch("/categories/{category_id}")
async def admin_update_category(
    category_id: str,
    payload: CategoryUpdateIn,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    category = await session.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="category_not_found")
    data = payload.model_dump(exclude_unset=True)
    translations = data.pop("translations", None)
    if "parent_id" in data:
        data["parent_id"] = await _category_parent(
            session,
            category.kind,
            category.department,
            data["parent_id"],
            category.slug,
            category.id,
        )
    effective_parent_id = data.get("parent_id", category.parent_id)
    effective_active = data.get("is_active", category.is_active)
    if effective_active and effective_parent_id:
        parent = await session.get(Category, effective_parent_id)
        if parent and not parent.is_active:
            _bad_request("parent_inactive")
    if data.get("is_active") is False:
        active_children = await session.scalar(
            select(func.count(Category.id)).where(
                Category.parent_id == category.id,
                Category.is_active.is_(True),
            )
        )
        if active_children:
            _bad_request("active_children_present")
    if translations:
        unknown = set(translations) - set(LOCALES)
        if unknown:
            _bad_request("invalid_locale", {"locales": sorted(unknown)})
        existing = {
            t.locale: t
            for t in (
                await session.execute(
                    select(CategoryTranslation).where(CategoryTranslation.category_id == category.id)
                )
            ).scalars().all()
        }
        for locale, tr in (payload.translations or {}).items():
            if locale in existing:
                existing[locale].name = tr.name
                existing[locale].description = tr.description
            else:
                session.add(
                    CategoryTranslation(category_id=category.id, locale=locale,
                                        name=tr.name, description=tr.description)
                )
    if "media_id" in data:
        data["image_url"] = await _resolve_media_url(session, data["media_id"])
    elif "image_url" in data:
        _validate_local_media_url(data["image_url"])
    for field in ("parent_id", "sort_order", "media_id", "image_url", "is_active"):
        if field in data:
            setattr(category, field, data[field])
    await audit(session, user.id, "admin.category.update", "category", category.id, None)
    await session.commit()
    return await _category_payload(session, category)


@router.delete("/categories/{category_id}")
async def admin_delete_category(
    category_id: str,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    category = await session.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="category_not_found")
    products = await session.scalar(
        select(func.count(Product.id)).where(Product.category_id == category.id)
    )
    children = await session.scalar(
        select(func.count(Category.id)).where(Category.parent_id == category.id)
    )
    if products or children:
        raise HTTPException(
            status_code=409,
            detail={"error": "category_in_use", "products": int(products or 0),
                    "children": int(children or 0)},
        )
    await session.delete(category)
    await audit(session, user.id, "admin.category.delete", "category", category_id, None)
    await session.commit()
    return {"deleted": True}


# ------------------------------ orders -------------------------------------


@router.get("/orders")
async def admin_list_orders(
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    q: Optional[str] = Query(default=None, max_length=80),
    status: Optional[str] = Query(default=None),
    payment_state: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    base = select(Order)
    count_q = select(func.count(Order.id))
    if q:
        base = base.where(Order.order_number.ilike(f"%{q}%"))
        count_q = count_q.where(Order.order_number.ilike(f"%{q}%"))
    if status:
        base = base.where(Order.status == status)
        count_q = count_q.where(Order.status == status)
    if payment_state:
        base = base.where(Order.payment_state == payment_state)
        count_q = count_q.where(Order.payment_state == payment_state)
    total = await session.scalar(count_q)
    rows = (
        await session.execute(
            base.order_by(Order.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    items = []
    for order in rows:
        count = await session.scalar(
            select(func.count(OrderItem.id)).where(OrderItem.order_id == order.id)
        )
        addr = order.shipping_address or {}
        items.append(
            {
                "order_number": order.order_number,
                "created_at": order.created_at,
                "status": order.status,
                "payment_state": order.payment_state,
                "grand_total": order.grand_total,
                "currency": order.currency,
                "item_count": int(count or 0),
                "email": order.guest_email,
                "recipient": addr.get("recipient_name"),
                "is_guest": order.user_id is None,
            }
        )
    return {"items": items, "total": int(total or 0), "page": page, "page_size": page_size}


@router.get("/orders/{order_number}")
async def admin_get_order(
    order_number: str,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    order = await session.scalar(select(Order).where(Order.order_number == order_number))
    if not order:
        raise HTTPException(status_code=404, detail="order_not_found")
    items = (
        await session.execute(
            select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id)
        )
    ).scalars().all()
    payment = await session.scalar(select(Payment).where(Payment.order_id == order.id))
    fulfillments = (
        await session.execute(
            select(SellerOrderFulfillment).where(SellerOrderFulfillment.order_id == order.id)
        )
    ).scalars().all()
    return {
        "order_number": order.order_number,
        "created_at": order.created_at,
        "status": order.status,
        "payment_state": order.payment_state,
        "currency": order.currency,
        "subtotal": order.subtotal,
        "shipping_amount": order.shipping_amount,
        "shipping_method": order.shipping_method,
        "grand_total": order.grand_total,
        "email": order.guest_email,
        "user_id": order.user_id,
        "shipping_address": order.shipping_address or {},
        "items": [
            {
                "product_name": i.product_name, "sku": i.sku,
                "option_values": i.option_values or {}, "image_url": i.image_url,
                "unit_price": i.unit_price, "quantity": i.quantity,
                "line_total": i.line_total, "seller_id": i.seller_id,
            }
            for i in items
        ],
        "payment": (
            {
                "id": payment.id,
                "status": payment.status,
                "amount": payment.amount,
                "merchant_trans_id": payment.merchant_trans_id,
                "failure_code": payment.failure_code,
                "failure_note": payment.failure_note,
                "paid_at": payment.paid_at,
                "review_note": payment.review_note,
            }
            if payment
            else None
        ),
        "legacy_fulfillments": [
            {"seller_id": f.seller_id, "status": f.status,
             "tracking_number": f.tracking_number, "shipping_carrier": f.shipping_carrier}
            for f in fulfillments
        ],
    }


class OrderStatusIn(BaseModel):
    status: str


@router.patch("/orders/{order_number}/status")
async def admin_update_order_status(
    order_number: str,
    payload: OrderStatusIn,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    order = await session.scalar(
        select(Order).where(Order.order_number == order_number).with_for_update()
    )
    if not order:
        raise HTTPException(status_code=404, detail="order_not_found")
    # payment integrity gate: unpaid / review / cancelled never fulfill
    if order.payment_state != "paid":
        raise HTTPException(
            status_code=409,
            detail={"error": "payment_not_eligible", "payment_state": order.payment_state},
        )
    expected = ORDER_TRANSITIONS.get(order.status)
    if payload.status != expected:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_transition", "current": order.status,
                    "allowed": [expected] if expected else []},
        )
    previous_status = order.status
    order.status = payload.status
    await audit(session, user.id, "admin.order.status", "order", order.order_number,
                {"from": previous_status, "to": payload.status})
    await session.commit()
    return {"order_number": order.order_number, "status": order.status}


# ------------------------------ customers ----------------------------------


@router.get("/customers")
async def admin_list_customers(
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    q: Optional[str] = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    base = select(User).where(User.role == "customer")
    count_q = select(func.count(User.id)).where(User.role == "customer")
    if q:
        like = f"%{q}%"
        cond = or_(User.email.ilike(like), User.first_name.ilike(like), User.last_name.ilike(like))
        base = base.where(cond)
        count_q = count_q.where(cond)
    total = await session.scalar(count_q)
    rows = (
        await session.execute(
            base.order_by(User.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    items = []
    for customer in rows:
        orders = await session.scalar(
            select(func.count(Order.id)).where(Order.user_id == customer.id)
        )
        items.append(
            {
                "id": customer.id,
                "email": customer.email,
                "first_name": customer.first_name,
                "last_name": customer.last_name,
                "preferred_locale": customer.preferred_locale,
                "is_active": customer.is_active,
                "created_at": customer.created_at,
                "order_count": int(orders or 0),
            }
        )
    return {"items": items, "total": int(total or 0), "page": page, "page_size": page_size}


@router.get("/customers/{customer_id}")
async def admin_get_customer(
    customer_id: str,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    customer = await session.get(User, customer_id)
    if not customer or customer.role != "customer":
        raise HTTPException(status_code=404, detail="customer_not_found")
    orders = (
        await session.execute(
            select(Order).where(Order.user_id == customer.id).order_by(Order.created_at.desc())
        )
    ).scalars().all()
    return {
        "id": customer.id,
        "email": customer.email,
        "first_name": customer.first_name,
        "last_name": customer.last_name,
        "preferred_locale": customer.preferred_locale,
        "is_active": customer.is_active,
        "created_at": customer.created_at,
        "orders": [
            {
                "order_number": o.order_number, "created_at": o.created_at,
                "status": o.status, "payment_state": o.payment_state,
                "grand_total": o.grand_total, "currency": o.currency,
            }
            for o in orders
        ],
    }


# ------------------------------ payment review ------------------------------


def _safe_event(event: PaymentEvent) -> dict:
    return {
        "event_type": event.event_type,
        "result": event.result,
        "provider_error_code": event.provider_error_code,
        "created_at": event.created_at,
    }


@router.get("/payments/review")
async def admin_payment_review_queue(
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    rows = (
        await session.execute(
            select(Payment, Order)
            .join(Order, Payment.order_id == Order.id)
            .where(
                or_(Payment.status == "reconciliation_required",
                    Order.status == "payment_review")
            )
            .order_by(Payment.created_at.desc())
        )
    ).all()
    items = []
    for payment, order in rows:
        events = (
            await session.execute(
                select(PaymentEvent)
                .where(PaymentEvent.payment_id == payment.id)
                .order_by(PaymentEvent.created_at.desc())
                .limit(5)
            )
        ).scalars().all()
        items.append(
            {
                "payment_id": payment.id,
                "order_number": order.order_number,
                "merchant_trans_id": payment.merchant_trans_id,
                "amount": payment.amount,
                "currency": payment.currency,
                "payment_status": payment.status,
                "order_status": order.status,
                "failure_code": payment.failure_code,
                "failure_note": payment.failure_note,
                "review_note": payment.review_note,
                "reviewed_by": payment.reviewed_by,
                "reviewed_at": payment.reviewed_at,
                "created_at": payment.created_at,
                "events": [_safe_event(e) for e in events],
            }
        )
    return {"items": items, "total": len(items)}


class ReviewNoteIn(BaseModel):
    note: str = Field(min_length=1, max_length=1000)


@router.post("/payments/{payment_id}/review-note")
async def admin_payment_review_note(
    payment_id: str,
    payload: ReviewNoteIn,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    payment = await session.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="payment_not_found")
    payment.review_note = payload.note
    payment.reviewed_by = user.id
    payment.reviewed_at = _now()
    await audit(session, user.id, "admin.payment.review_note", "payment", payment.id, None)
    await session.commit()
    return {"payment_id": payment.id, "review_note": payment.review_note}


# ------------------------------ audit / settings ----------------------------


@router.get("/audit")
async def admin_audit_log(
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
):
    from db.models import CmsAuditLog

    total = await session.scalar(select(func.count(CmsAuditLog.id)))
    rows = (
        await session.execute(
            select(CmsAuditLog)
            .order_by(CmsAuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    actor_ids = {r.actor_user_id for r in rows if r.actor_user_id}
    actors = {}
    if actor_ids:
        users = (
            await session.execute(select(User).where(User.id.in_(actor_ids)))
        ).scalars().all()
        actors = {u.id: u.email for u in users}
    return {
        "items": [
            {
                "id": r.id,
                "actor": actors.get(r.actor_user_id, r.actor_user_id),
                "action": r.action,
                "target_type": r.target_type,
                "target_id": r.target_id,
                "metadata": r.safe_metadata,
                "created_at": r.created_at,
            }
            for r in rows
        ],
        "total": int(total or 0),
        "page": page,
        "page_size": page_size,
    }


@router.get("/settings")
async def admin_settings(user: User = Depends(require_admin)):
    import os

    from shipping.mock import FREE_STANDARD_THRESHOLD, _METHODS

    return {
        "store": "MUSLIMAH CANTIK",
        "business_model": "single_vendor",
        "currency": BASE_CURRENCY,
        "checkout_enabled": CHECKOUT_ENABLED,
        "payment_status": "disabled",
        "shipping_provider": SHIPPING_PROVIDER,
        "shipping_methods": list(_METHODS),
        "free_standard_threshold": FREE_STANDARD_THRESHOLD,
        "inventory_reservation_ttl_minutes": INVENTORY_RESERVATION_TTL_MINUTES,
        "media_storage": os.environ.get("MEDIA_STORAGE", "local"),
        "locales": list(LOCALES),
    }
