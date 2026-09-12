"""Milestone 2 - Catalog API tests for MUSLIMAH CANTIK"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
API = f"{BASE_URL}/api/v1/catalog"

# Some CDNs block default python-requests UA; use a browser-like UA
HEADERS = {"User-Agent": "Mozilla/5.0 (Testing) AppleWebKit/537.36"}


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update(HEADERS)
    return sess


# ---------- Health ----------
def test_health(s):
    r = s.get(f"{BASE_URL}/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["db"] == "up"


def test_status(s):
    r = s.get(f"{BASE_URL}/api/status")
    # The public API intentionally exposes only the liveness/readiness
    # endpoints.  Keep this aligned with the production smoke contract so a
    # generic status/debug surface is not accidentally reintroduced.
    assert r.status_code == 404


# ---------- Departments ----------
def test_departments(s):
    r = s.get(f"{API}/departments")
    assert r.status_code == 200
    depts = r.json()
    slugs = sorted([d["slug"] for d in depts])
    assert slugs == sorted(["women-muslimah", "uniqlo-products", "tropical-halal-skincare"]), slugs


# ---------- Categories by department ----------
def test_categories_women_muslimah(s):
    r = s.get(f"{API}/categories", params={"department": "women-muslimah"})
    assert r.status_code == 200
    cats = r.json()
    slugs = {c["slug"] for c in cats}
    assert len(cats) == 17, f"Expected 17, got {len(cats)}: {slugs}"
    for need in ["hijab-kerudung", "gamis", "abaya", "mukena", "busana-syari", "busana-muslimah-anak"]:
        assert need in slugs, f"Missing {need}"


def test_categories_uniqlo(s):
    r = s.get(f"{API}/categories", params={"department": "uniqlo-products"})
    assert r.status_code == 200
    slugs = sorted([c["slug"] for c in r.json()])
    expected = sorted(["outerwear", "tshirts-sweats-fleece", "sweatshirts-hoodies", "bottoms",
                       "shirts-blouses", "sweaters-knitwear", "dresses-skirts", "loungewear-home"])
    assert slugs == expected, slugs


def test_categories_skincare(s):
    r = s.get(f"{API}/categories", params={"department": "tropical-halal-skincare"})
    assert r.status_code == 200
    slugs = sorted([c["slug"] for c in r.json()])
    expected = sorted(["facial-wash", "moist-cream", "sunscreen", "serum", "face-mist"])
    assert slugs == expected, slugs


# ---------- Category detail (BUG FIX) ----------
def test_category_detail_hijab_kerudung(s):
    r = s.get(f"{API}/categories/hijab-kerudung")
    assert r.status_code == 200
    data = r.json()
    assert "department" in data and data["department"] is not None, "department is null (ObjectId bug)"
    assert data["department"]["slug"] == "women-muslimah"
    assert "product_count" in data
    # localization
    tr = data.get("translations", {})
    assert all(k in tr for k in ["id", "en", "uz", "ru"]), f"Missing locales: {list(tr.keys())}"


def test_category_detail_404(s):
    r = s.get(f"{API}/categories/nonexistent-slug-xyz")
    assert r.status_code == 404


# ---------- Product detail (BUG FIX) ----------
def test_product_detail_hoodie(s):
    r = s.get(f"{API}/products/gray-sweat-oversized-full-zip-hoodie")
    assert r.status_code == 200
    data = r.json()
    assert data.get("category") is not None, "category is null (ObjectId bug)"
    assert data["category"]["slug"] == "sweatshirts-hoodies"
    assert data["base_price"] == 499000
    assert data.get("seller_id")
    variants = data.get("variants", [])
    assert len(variants) == 24, f"Expected 24 variants, got {len(variants)}"

    # colors and sizes
    colors = {v["option_values"].get("color") for v in variants}
    sizes = {v["option_values"].get("size") for v in variants}
    assert colors == {"Gray", "Black", "Beige", "Navy"}, colors
    assert sizes == {"XS", "S", "M", "L", "XL", "XXL"}, sizes

    # XXL variants have price_override 519000
    xxl = [v for v in variants if v["option_values"].get("size") == "XXL"]
    assert len(xxl) == 4
    for v in xxl:
        assert v.get("price_override") == 519000, v

    by_sku = {v["sku"]: v for v in variants}
    assert by_sku["GSOZH-BLK-XXL"]["stock_quantity"] == 0
    assert by_sku["GSOZH-GRY-XS"]["stock_quantity"] == 2

    # Localization
    tr = data.get("translations", {})
    assert all(k in tr for k in ["id", "en", "uz", "ru"]), list(tr.keys())


def test_product_detail_404(s):
    r = s.get(f"{API}/products/nonexistent-slug-xyz")
    assert r.status_code == 404


# ---------- Flexible variants ----------
def test_premium_chiffon_hijab_variants(s):
    r = s.get(f"{API}/products/premium-chiffon-hijab")
    assert r.status_code == 200
    variants = r.json().get("variants", [])
    assert len(variants) >= 1
    for v in variants:
        ov = v["option_values"]
        assert "color" in ov and "material" in ov
        assert ov["material"] in ("Voal", "Chiffon")
    # Requirement mentions {color: Black, material: Voal} exists
    combos = {(v["option_values"]["color"], v["option_values"]["material"]) for v in variants}
    assert ("Black", "Voal") in combos


def test_halal_facial_wash_variants(s):
    r = s.get(f"{API}/products/halal-gentle-facial-wash")
    assert r.status_code == 200
    variants = r.json().get("variants", [])
    fifty = [v for v in variants if v["option_values"].get("volume") == "50 ml"]
    assert len(fifty) == 1
    assert fifty[0].get("price_override") == 49000


def test_kids_set_size_only(s):
    r = s.get(f"{API}/products/kids-muslimah-daily-set")
    assert r.status_code == 200
    variants = r.json().get("variants", [])
    assert len(variants) >= 1
    for v in variants:
        ov = v["option_values"]
        assert "size" in ov
        # size-only means no color/material
        assert "color" not in ov


# ---------- Stock states ----------
def test_stock_state_out_of_stock(s):
    # tropical-moist-cream-50ml - listed in requirements as out_of_stock at product level
    # Find via products list first
    r = s.get(f"{API}/products", params={"limit": 50})
    assert r.status_code == 200
    products = r.json().get("items", r.json() if isinstance(r.json(), list) else [])
    match = [p for p in products if p["slug"] == "tropical-moist-cream-50ml"]
    assert match, "product tropical-moist-cream-50ml not found in list"
    assert match[0].get("stock_state") == "out_of_stock", match[0].get("stock_state")


# ---------- Badges ----------
def test_badge_sale(s):
    r = s.get(f"{API}/products", params={"badge": "sale"})
    assert r.status_code == 200
    data = r.json()
    items = data.get("items", data)
    assert len(items) >= 1
    for p in items:
        assert p.get("compare_at_price"), p


def test_badge_new(s):
    r = s.get(f"{API}/products", params={"badge": "new"})
    assert r.status_code == 200
    items = r.json().get("items", [])
    assert len(items) == 4, f"Expected 4 new, got {len(items)}"


def test_badge_bestseller(s):
    r = s.get(f"{API}/products", params={"badge": "bestseller"})
    assert r.status_code == 200
    items = r.json().get("items", [])
    assert len(items) == 4, f"Expected 4 bestseller, got {len(items)}"


# ---------- Pagination / sort / search ----------
def test_pagination(s):
    r1 = s.get(f"{API}/products", params={"page": 1, "limit": 5})
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1.get("total") == 12
    assert d1.get("pages") == 3
    assert len(d1.get("items", [])) == 5
    r2 = s.get(f"{API}/products", params={"page": 2, "limit": 5})
    assert len(r2.json().get("items", [])) == 5


def test_sort_price_asc(s):
    r = s.get(f"{API}/products", params={"sort": "price_asc", "limit": 50})
    items = r.json().get("items", [])
    assert items[0]["slug"] == "halal-gentle-facial-wash", items[0]["slug"]


def test_search_hoodie(s):
    r = s.get(f"{API}/products", params={"q": "hoodie"})
    items = r.json().get("items", [])
    assert len(items) == 1
    assert items[0]["slug"] == "gray-sweat-oversized-full-zip-hoodie"
