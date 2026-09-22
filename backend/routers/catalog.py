import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import (
    Category,
    Product,
    ProductTranslation,
    ProductVariant,
)
from db.session import get_session
from config import PREORDER_ESTIMATE_DAYS
from taxonomy import (
    active_taxonomy_chain,
    active_taxonomy_ids_select,
    descendant_ids_select,
    get_category_ancestors,
    get_root_category,
)

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])

SORTS = {
    # Every public list has a unique final key. This keeps page boundaries
    # stable when multiple products share the same merchandising value.
    "featured": (Product.featured.desc(), Product.created_at.desc(), Product.id.desc()),
    "newest": (Product.created_at.desc(), Product.id.desc()),
    "price_asc": (Product.base_price.asc(), Product.id.asc()),
    "price_desc": (Product.base_price.desc(), Product.id.asc()),
    "name": (Product.slug.asc(), Product.id.asc()),
}


def _stock_state(total_stock: int) -> str:
    # Kept as a compatibility field for older clients. Public availability
    # is always pre-order and never reflects internal inventory.
    return "pre_order"


def _translations(obj) -> dict:
    out = {}
    for t in obj.translations:
        entry = {"title": t.name}
        if t.description:
            entry["description"] = t.description
        out[t.locale] = entry
    return out


def _category_out(c: Category) -> dict:
    return {
        "id": c.id,
        "kind": c.kind,
        "department": c.department,
        "slug": c.slug,
        "parent_id": c.parent_id,
        "media_id": c.media_id,
        "image_url": c.image_url,
        "sort_order": c.sort_order,
        "is_active": c.is_active,
        "translations": _translations(c),
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    }


def _product_out(p: Product) -> dict:
    return {
        "id": p.id,
        "seller_id": p.seller_id,
        "category_id": p.category_id,
        "product_type": p.product_type,
        "slug": p.slug,
        "brand": p.brand,
        "base_price": p.base_price,
        "compare_at_price": p.compare_at_price,
        "currency": p.currency,
        "attributes": p.attributes or {},
        "tags": p.tags or [],
        "media": p.media or [],
        "status": p.status,
        "is_demo": False,
        "ordering_mode": "pre_order",
        "preorder_estimate_days": PREORDER_ESTIMATE_DAYS,
        "featured": p.featured,
        "bestseller": p.bestseller,
        "new_arrival": p.new_arrival,
        "translations": _translations(p),
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


def _variant_out(v: ProductVariant) -> dict:
    stock_quantity = max(int(v.stock_quantity or 0), 0)
    return {
        "id": v.id,
        "product_id": v.product_id,
        "sku": v.sku,
        "option_values": v.option_values or {},
        "stock_quantity": stock_quantity,
        "price_override": v.price_override,
        "sale_price_override": v.sale_price_override,
        "media_id": v.media_id,
        "image_url": v.image_url,
        "is_active": v.is_active,
        "stock_state": _stock_state(stock_quantity) if v.is_active else "inactive",
        "created_at": v.created_at,
        "updated_at": v.updated_at,
    }


async def _variant_stats(session: AsyncSession, product_ids: list) -> dict:
    if not product_ids:
        return {}
    stats_stmt = (
        select(
            ProductVariant.product_id,
            func.count().label("cnt"),
            func.coalesce(func.sum(ProductVariant.stock_quantity), 0).label("stock"),
        )
        .where(
            ProductVariant.product_id.in_(product_ids),
            ProductVariant.is_active.is_(True),
        )
        .group_by(ProductVariant.product_id)
    )
    colors_stmt = (
        select(
            ProductVariant.product_id,
            ProductVariant.option_values["color"].astext.label("color"),
        )
        .where(
            ProductVariant.product_id.in_(product_ids),
            ProductVariant.is_active.is_(True),
            ProductVariant.option_values.has_key("color"),
        )
        .distinct()
    )
    stats_rows = (await session.execute(stats_stmt)).all()
    color_rows = (await session.execute(colors_stmt)).all()
    colors_by_product: dict = {}
    for pid, color in color_rows:
        # JSONB may contain a null value for a malformed legacy option. Do
        # not let one row make the entire catalog response fail to serialize.
        if color is not None:
            colors_by_product.setdefault(pid, set()).add(color)
    result = {}
    for pid, cnt, stock in stats_rows:
        total_stock = max(int(stock or 0), 0)
        result[pid] = {
            "variant_count": cnt,
            "total_stock": total_stock,
            "stock_state": _stock_state(total_stock),
            "colors": sorted(colors_by_product.get(pid, set())),
        }
    return result


_EMPTY_STATS = {
    "variant_count": 0,
    "total_stock": 0,
    "stock_state": "pre_order",
    "colors": [],
}


async def _scope_filters(
    session: AsyncSession,
    department: Optional[str],
    category: Optional[str],
) -> list:
    filters = [
        Product.status == "active",
        Product.category_id.in_(
            select(Category.id).where(
                Category.kind == "category",
                Category.id.in_(active_taxonomy_ids_select()),
            )
        ),
    ]
    if category:
        cat = await session.scalar(
            select(Category).where(
                Category.slug == category,
                Category.is_active.is_(True),
            )
        )
        if not cat:
            raise HTTPException(status_code=404, detail="Category not found")
        if not await active_taxonomy_chain(session, cat):
            raise HTTPException(status_code=404, detail="Category not found")
        if department:
            dept = await session.scalar(
                select(Category).where(
                    Category.slug == department,
                    Category.kind == "department",
                    Category.parent_id.is_(None),
                    Category.is_active.is_(True),
                    Category.department == Category.slug,
                )
            )
            if not dept:
                raise HTTPException(status_code=404, detail="Department not found")
            root = await get_root_category(session, cat)
            if not root or root.id != dept.id:
                raise HTTPException(status_code=404, detail="Category not found")
        filters.append(
            Product.category_id.in_(
                select(Category.id)
                .where(
                    Category.id.in_(descendant_ids_select(cat.id, active_only=True)),
                    Category.kind == "category",
                    Category.is_active.is_(True),
                )
            )
        )
    elif department:
        dept = await session.scalar(
            select(Category).where(
                Category.slug == department,
                Category.kind == "department",
                Category.parent_id.is_(None),
                Category.is_active.is_(True),
                Category.department == Category.slug,
            )
        )
        if not dept:
            raise HTTPException(status_code=404, detail="Department not found")
        filters.append(
            Product.category_id.in_(
                select(Category.id).where(
                    Category.id.in_(descendant_ids_select(dept.id, active_only=True)),
                    Category.kind == "category",
                    Category.is_active.is_(True),
                )
            )
        )
    return filters


def _validate_catalog_query(
    *, badge: Optional[str], availability: Optional[str], sort: str,
    min_price: Optional[int], max_price: Optional[int]
) -> None:
    if badge and badge not in {"new", "bestseller", "featured", "sale"}:
        raise HTTPException(status_code=400, detail="invalid_badge")
    if availability and availability not in {"in_stock", "out_of_stock"}:
        raise HTTPException(status_code=400, detail="invalid_availability")
    if sort not in SORTS:
        raise HTTPException(status_code=400, detail="invalid_sort")
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(status_code=400, detail="invalid_price_range")


def _variant_exists_clause(**conditions):
    stmt = select(ProductVariant.id).where(
        ProductVariant.product_id == Product.id,
        ProductVariant.is_active.is_(True),
    )
    for cond in conditions.values():
        stmt = stmt.where(cond)
    return stmt.exists()


@router.get("/departments")
async def list_departments(session: AsyncSession = Depends(get_session)):
    stmt = (
        select(Category)
        .options(selectinload(Category.translations))
        .where(
            Category.kind == "department",
            Category.parent_id.is_(None),
            Category.is_active.is_(True),
            Category.department == Category.slug,
        )
        .order_by(Category.sort_order, Category.slug)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_category_out(c) for c in rows]


def _sort_category_nodes(nodes: list[dict]) -> list[dict]:
    for node in nodes:
        node["children"] = _sort_category_nodes(node.get("children", []))
    return sorted(nodes, key=lambda item: (item.get("sort_order", 0), item.get("slug", "")))


@router.get("/tree")
async def catalog_tree(session: AsyncSession = Depends(get_session)):
    """Return the active department -> category navigation tree."""

    rows = (
        await session.execute(
            select(Category)
            .options(selectinload(Category.translations))
            .where(
                Category.is_active.is_(True),
                Category.kind.in_(("department", "category")),
                Category.id.in_(active_taxonomy_ids_select()),
            )
        )
    ).scalars().all()
    nodes = {category.id: {**_category_out(category), "children": []} for category in rows}
    roots = []
    for category in rows:
        node = nodes[category.id]
        if category.parent_id and category.parent_id in nodes:
            nodes[category.parent_id]["children"].append(node)
        elif category.kind == "department":
            roots.append(node)
    return _sort_category_nodes(roots)


@router.get("/categories")
async def list_categories(
    department: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(Category)
        .options(selectinload(Category.translations))
        .where(Category.kind == "category", Category.is_active.is_(True))
        .order_by(Category.sort_order, Category.slug)
    )
    if department:
        dept = await session.scalar(
            select(Category).where(
                Category.slug == department,
                Category.kind == "department",
                Category.parent_id.is_(None),
                Category.is_active.is_(True),
                Category.department == Category.slug,
            )
        )
        if not dept:
            raise HTTPException(status_code=404, detail="Department not found")
        stmt = stmt.where(
            Category.id.in_(descendant_ids_select(dept.id, active_only=True))
        )
    rows = (await session.execute(stmt)).scalars().all()
    return [_category_out(c) for c in rows]


@router.get("/categories/{slug}")
async def category_detail(slug: str, session: AsyncSession = Depends(get_session)):
    stmt = (
        select(Category)
        .options(selectinload(Category.translations))
        .where(Category.slug == slug, Category.is_active.is_(True))
    )
    cat = (await session.execute(stmt)).scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    if not await active_taxonomy_chain(session, cat):
        raise HTTPException(status_code=404, detail="Category not found")
    out = _category_out(cat)
    ancestors = await get_category_ancestors(session, cat, active_only=True)
    ancestor_ids = [ancestor.id for ancestor in ancestors]
    loaded_ancestors = {}
    if ancestor_ids:
        ancestor_rows = (
            await session.execute(
                select(Category)
                .options(selectinload(Category.translations))
                .where(Category.id.in_(ancestor_ids))
            )
        ).scalars().all()
        loaded_ancestors = {ancestor.id: ancestor for ancestor in ancestor_rows}
    ordered_ancestors = [loaded_ancestors[item.id] for item in ancestors if item.id in loaded_ancestors]
    out["ancestors"] = [_category_out(item) for item in ordered_ancestors]
    department_node = ordered_ancestors[0] if ordered_ancestors else (
        cat if cat.kind == "department" else None
    )
    out["department"] = _category_out(department_node) if department_node else None
    valid_child_kinds = {"department": ("category",), "category": ()}.get(cat.kind)
    if valid_child_kinds is None:
        raise HTTPException(status_code=404, detail="Category not found")
    children = []
    if valid_child_kinds:
        children = (
            await session.execute(
                select(Category)
                .options(selectinload(Category.translations))
                .where(
                    Category.parent_id == cat.id,
                    Category.department == cat.department,
                    Category.kind.in_(valid_child_kinds),
                    Category.is_active.is_(True),
                    Category.id.in_(active_taxonomy_ids_select()),
                )
                .order_by(Category.sort_order, Category.slug)
            )
        ).scalars().all()
    out["children"] = [_category_out(child) for child in children]
    out["product_count"] = int(await session.scalar(
        select(func.count())
        .select_from(Product)
        .where(
            Product.category_id.in_(
                select(Category.id)
                .where(
                    Category.id.in_(descendant_ids_select(cat.id, active_only=True)),
                    Category.kind == "category",
                    Category.is_active.is_(True),
                )
            ),
            Product.status == "active",
        )
    ) or 0)
    return out


@router.get("/filters")
async def filter_metadata(
    department: Optional[str] = Query(default=None, max_length=120),
    category: Optional[str] = Query(default=None, max_length=120),
    session: AsyncSession = Depends(get_session),
):
    filters = await _scope_filters(session, department, category)
    pid_subq = select(Product.id).where(*filters).scalar_subquery()
    price = (
        await session.execute(
            select(
                func.coalesce(func.min(Product.base_price), 0),
                func.coalesce(func.max(Product.base_price), 0),
            ).where(*filters)
        )
    ).one()

    async def distinct_option(key: str) -> list:
        stmt = (
            select(ProductVariant.option_values[key].astext)
            .where(
                ProductVariant.product_id.in_(pid_subq),
                ProductVariant.is_active.is_(True),
                ProductVariant.option_values.has_key(key),
            )
            .distinct()
        )
        rows = (await session.execute(stmt)).scalars().all()
        return sorted(v for v in rows if v)

    return {
        "colors": await distinct_option("color"),
        "sizes": await distinct_option("size"),
        "volumes": await distinct_option("volume"),
        "motifs": await distinct_option("motif"),
        "formats": await distinct_option("format"),
        "price": {"min": int(price[0]), "max": int(price[1])},
    }


@router.get("/products")
async def list_products(
    department: Optional[str] = Query(default=None, max_length=120),
    category: Optional[str] = Query(default=None, max_length=120),
    q: Optional[str] = Query(default=None, max_length=120),
    badge: Optional[str] = Query(default=None, max_length=20),
    min_price: Optional[int] = Query(None, ge=0),
    max_price: Optional[int] = Query(None, ge=0),
    color: Optional[str] = Query(default=None, max_length=120),
    size: Optional[str] = Query(default=None, max_length=120),
    volume: Optional[str] = Query(default=None, max_length=120),
    motif: Optional[str] = Query(default=None, max_length=120),
    format: Optional[str] = Query(default=None, max_length=120),
    availability: Optional[str] = Query(default=None, max_length=20),
    ids: Optional[str] = Query(default=None, max_length=2200),
    sort: str = Query(default="featured", max_length=20),
    page: int = Query(1, ge=1),
    limit: int = Query(12, ge=1, le=60),
    session: AsyncSession = Depends(get_session),
):
    _validate_catalog_query(
        badge=badge,
        availability=availability,
        sort=sort,
        min_price=min_price,
        max_price=max_price,
    )
    filters = await _scope_filters(session, department, category)

    if ids:
        product_ids = [item.strip() for item in ids.split(",") if item.strip()]
        if not product_ids or len(product_ids) > 60 or any(
            not re.fullmatch(r"[A-Za-z0-9_-]{8,40}", item) for item in product_ids
        ):
            raise HTTPException(status_code=400, detail="invalid_product_ids")
        filters.append(Product.id.in_(product_ids))

    if badge == "new":
        filters.append(Product.new_arrival.is_(True))
    elif badge == "bestseller":
        filters.append(Product.bestseller.is_(True))
    elif badge == "featured":
        filters.append(Product.featured.is_(True))
    elif badge == "sale":
        filters.append(Product.compare_at_price.isnot(None))
    if min_price is not None:
        filters.append(Product.base_price >= min_price)
    if max_price is not None:
        filters.append(Product.base_price <= max_price)
    if color:
        filters.append(
            _variant_exists_clause(
                color=ProductVariant.option_values["color"].astext == color
            )
        )
    if size:
        filters.append(
            _variant_exists_clause(
                size=ProductVariant.option_values["size"].astext == size
            )
        )
    for option_key, option_value in (("volume", volume), ("motif", motif), ("format", format)):
        if option_value:
            filters.append(
                _variant_exists_clause(
                    **{option_key: ProductVariant.option_values[option_key].astext == option_value}
                )
            )
    # Availability is retained as a deprecated query parameter for old
    # clients, but inventory never filters pre-order catalog results.
    if q:
        like = f"%{q}%"
        filters.append(
            or_(
                Product.slug.ilike(like),
                Product.brand.ilike(like),
                func.cast(Product.tags, String).ilike(like),
                Product.id.in_(
                    select(ProductTranslation.product_id).where(
                        ProductTranslation.name.ilike(like)
                    )
                ),
                Product.id.in_(
                    select(ProductVariant.product_id).where(
                        ProductVariant.sku.ilike(like)
                    )
                ),
            )
        )

    total = await session.scalar(select(func.count()).select_from(Product).where(*filters))
    order = SORTS[sort]
    stmt = (
        select(Product)
        .options(selectinload(Product.translations))
        .where(*filters)
        .order_by(*order)
        .offset((page - 1) * limit)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    stats = await _variant_stats(session, [p.id for p in rows])
    items = []
    for p in rows:
        data = _product_out(p)
        data.update(stats.get(p.id, _EMPTY_STATS))
        items.append(data)
    return {
        "items": items,
        "total": total or 0,
        "page": page,
        "limit": limit,
        "pages": ((total or 0) + limit - 1) // limit,
    }


@router.get("/products/{slug}")
async def product_detail(slug: str, session: AsyncSession = Depends(get_session)):
    stmt = (
        select(Product)
        .options(
            selectinload(Product.translations),
            selectinload(Product.variants),
        )
        .where(Product.slug == slug, Product.status == "active")
    )
    product = (await session.execute(stmt)).scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    out = _product_out(product)
    out["variants"] = [
        _variant_out(v)
        for v in sorted(product.variants, key=lambda v: (v.created_at, v.sku))
        if v.is_active
    ]
    out.update(
        (await _variant_stats(session, [product.id])).get(product.id, _EMPTY_STATS)
    )
    cat = (
        await session.execute(
            select(Category)
            .options(selectinload(Category.translations))
            .where(
                Category.id == product.category_id,
                Category.kind == "category",
                Category.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Product not found")
    if not await active_taxonomy_chain(session, cat):
        raise HTTPException(status_code=404, detail="Product not found")
    cat_out = _category_out(cat)
    ancestors = await get_category_ancestors(session, cat, active_only=True)
    ancestor_ids = [ancestor.id for ancestor in ancestors]
    loaded_ancestors = {}
    if ancestor_ids:
        ancestor_rows = (
            await session.execute(
                select(Category)
                .options(selectinload(Category.translations))
                .where(Category.id.in_(ancestor_ids))
            )
        ).scalars().all()
        loaded_ancestors = {ancestor.id: ancestor for ancestor in ancestor_rows}
    ordered_ancestors = [
        loaded_ancestors[item.id]
        for item in ancestors
        if item.id in loaded_ancestors
    ]
    cat_out["ancestors"] = [_category_out(item) for item in ordered_ancestors]
    department_node = ordered_ancestors[0] if ordered_ancestors else (
        cat if cat.kind == "department" else None
    )
    cat_out["department"] = _category_out(department_node) if department_node else None
    out["category"] = cat_out
    return out


@router.get("/products/{slug}/variants")
async def list_product_variants(
    slug: str, session: AsyncSession = Depends(get_session)
):
    product = await session.scalar(
        select(Product).where(Product.slug == slug, Product.status == "active")
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    category = await session.scalar(
        select(Category).where(
            Category.id == product.category_id,
            Category.kind == "category",
            Category.is_active.is_(True),
        )
    )
    if not category:
        raise HTTPException(status_code=404, detail="Product not found")
    if not await active_taxonomy_chain(session, category):
        raise HTTPException(status_code=404, detail="Product not found")
    stmt = (
        select(ProductVariant)
        .where(
            ProductVariant.product_id == product.id,
            ProductVariant.is_active.is_(True),
        )
        .order_by(ProductVariant.created_at, ProductVariant.sku)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_variant_out(v) for v in rows]
