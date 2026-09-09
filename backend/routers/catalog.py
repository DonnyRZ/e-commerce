from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query

from database import db
from models import Category, Product, ProductVariant

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])

LOW_STOCK_THRESHOLD = 5

SORTS = {
    "newest": ("created_at", -1),
    "price_asc": ("base_price", 1),
    "price_desc": ("base_price", -1),
    "name": ("slug", 1),
}


def _stock_state(total_stock: int) -> str:
    if total_stock <= 0:
        return "out_of_stock"
    if total_stock <= LOW_STOCK_THRESHOLD:
        return "low_stock"
    return "in_stock"


async def _variant_stats(product_id: str) -> dict:
    total_stock = 0
    count = 0
    cursor = db.product_variants.find(
        {"product_id": product_id, "is_active": True}, {"stock_quantity": 1}
    )
    async for v in cursor:
        total_stock += v.get("stock_quantity", 0)
        count += 1
    return {
        "variant_count": count,
        "total_stock": total_stock,
        "stock_state": _stock_state(total_stock) if count else "out_of_stock",
    }


async def _department_category_ids(dept_slug: str) -> list:
    dept = await db.categories.find_one({"slug": dept_slug, "kind": "department"})
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    ids = []
    async for c in db.categories.find({"parent_id": str(dept["_id"])}, {"_id": 1}):
        ids.append(str(c["_id"]))
    return ids


@router.get("/departments")
async def list_departments():
    cursor = db.categories.find({"kind": "department", "is_active": True}).sort(
        "sort_order", 1
    )
    return [Category.from_mongo(d).model_dump() async for d in cursor]


@router.get("/categories")
async def list_categories(department: Optional[str] = None):
    query = {"kind": "category", "is_active": True}
    if department:
        dept = await db.categories.find_one({"slug": department, "kind": "department"})
        if not dept:
            raise HTTPException(status_code=404, detail="Department not found")
        query["parent_id"] = str(dept["_id"])
    cursor = db.categories.find(query).sort("sort_order", 1)
    return [Category.from_mongo(d).model_dump() async for d in cursor]


@router.get("/categories/{slug}")
async def category_detail(slug: str):
    doc = await db.categories.find_one({"slug": slug, "is_active": True})
    if not doc:
        raise HTTPException(status_code=404, detail="Category not found")
    cat = Category.from_mongo(doc).model_dump()
    if cat.get("parent_id"):
        parent = await db.categories.find_one({"_id": ObjectId(cat["parent_id"])})
        cat["department"] = Category.from_mongo(parent).model_dump() if parent else None
    cat["product_count"] = await db.products.count_documents(
        {"category_id": cat["id"], "status": "active"}
    )
    return cat


@router.get("/products")
async def list_products(
    department: Optional[str] = None,
    category: Optional[str] = None,
    q: Optional[str] = None,
    badge: Optional[str] = None,
    sort: str = "newest",
    page: int = Query(1, ge=1),
    limit: int = Query(12, ge=1, le=60),
):
    query: dict = {"status": "active"}
    if category:
        cat = await db.categories.find_one({"slug": category})
        if not cat:
            raise HTTPException(status_code=404, detail="Category not found")
        query["category_id"] = str(cat["_id"])
    elif department:
        query["category_id"] = {"$in": await _department_category_ids(department)}
    if badge == "new":
        query["new_arrival"] = True
    elif badge == "bestseller":
        query["bestseller"] = True
    elif badge == "featured":
        query["featured"] = True
    elif badge == "sale":
        query["compare_at_price"] = {"$gt": 0}
    if q:
        query["$or"] = [
            {"slug": {"$regex": q, "$options": "i"}},
            {"tags": {"$regex": q, "$options": "i"}},
        ]

    sort_field, sort_dir = SORTS.get(sort, SORTS["newest"])
    total = await db.products.count_documents(query)
    cursor = (
        db.products.find(query)
        .sort(sort_field, sort_dir)
        .skip((page - 1) * limit)
        .limit(limit)
    )
    items = []
    async for doc in cursor:
        product = Product.from_mongo(doc).model_dump()
        product.update(await _variant_stats(product["id"]))
        items.append(product)
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
    }


@router.get("/products/{slug}")
async def product_detail(slug: str):
    doc = await db.products.find_one({"slug": slug, "status": "active"})
    if not doc:
        raise HTTPException(status_code=404, detail="Product not found")
    product = Product.from_mongo(doc).model_dump()
    variants = [
        ProductVariant.from_mongo(v).model_dump()
        async for v in db.product_variants.find({"product_id": product["id"]})
    ]
    product["variants"] = variants
    product.update(await _variant_stats(product["id"]))
    cat = await db.categories.find_one({"_id": ObjectId(product["category_id"])})
    product["category"] = Category.from_mongo(cat).model_dump() if cat else None
    return product


@router.get("/products/{slug}/variants")
async def list_product_variants(slug: str):
    doc = await db.products.find_one({"slug": slug}, {"_id": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Product not found")
    return [
        ProductVariant.from_mongo(v).model_dump()
        async for v in db.product_variants.find({"product_id": str(doc["_id"])})
    ]
