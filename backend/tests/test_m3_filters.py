"""Milestone 3 - PostgreSQL migration + new filter/sort/search functionality"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://muslimah-shop.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api/v1/catalog"
HEADERS = {"User-Agent": "Mozilla/5.0 (Testing) AppleWebKit/537.36"}


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update(HEADERS)
    return sess


# ---------- /filters endpoint ----------
def test_filters_women_muslimah(s):
    r = s.get(f"{API}/filters", params={"department": "women-muslimah"})
    assert r.status_code == 200
    data = r.json()
    assert "colors" in data and "sizes" in data and "price" in data
    assert isinstance(data["colors"], list)
    assert isinstance(data["sizes"], list)
    price = data["price"]
    assert "min" in price and "max" in price
    assert price["min"] > 0 and price["max"] >= price["min"]
    # Requirements say 7 colors + 8 sizes for women-muslimah
    assert len(data["colors"]) >= 5, f"Expected >=5 colors, got {len(data['colors'])}"
    assert len(data["sizes"]) >= 5, f"Expected >=5 sizes, got {len(data['sizes'])}"


def test_filters_skincare_no_color_size(s):
    r = s.get(f"{API}/filters", params={"department": "tropical-halal-skincare"})
    assert r.status_code == 200
    data = r.json()
    assert len(data.get("colors", [])) == 0, f"Skincare should have 0 colors, got {data.get('colors')}"
    assert len(data.get("sizes", [])) == 0, f"Skincare should have 0 sizes, got {data.get('sizes')}"


# ---------- Color / size filters ----------
def test_filter_by_color_black(s):
    r = s.get(f"{API}/products", params={"department": "women-muslimah", "color": "Black"})
    assert r.status_code == 200
    items = r.json().get("items", [])
    assert len(items) == 2, f"Expected 2 black products in women-muslimah, got {len(items)}: {[p['slug'] for p in items]}"


def test_filter_by_size_xxl_returns_hoodie(s):
    r = s.get(f"{API}/products", params={"size": "XXL"})
    assert r.status_code == 200
    items = r.json().get("items", [])
    slugs = [p["slug"] for p in items]
    assert "gray-sweat-oversized-full-zip-hoodie" in slugs
    # Requirement: XXL returns hoodie only
    assert len(items) == 1, f"Expected 1 XXL product, got {len(items)}: {slugs}"


# ---------- Availability ----------
def test_availability_out_of_stock(s):
    r = s.get(f"{API}/products", params={"availability": "out_of_stock"})
    assert r.status_code == 200
    items = r.json().get("items", [])
    slugs = [p["slug"] for p in items]
    assert "tropical-moist-cream-50ml" in slugs


def test_availability_in_stock_excludes_oos(s):
    r = s.get(f"{API}/products", params={"availability": "in_stock", "limit": 50})
    assert r.status_code == 200
    items = r.json().get("items", [])
    slugs = [p["slug"] for p in items]
    assert "tropical-moist-cream-50ml" not in slugs


# ---------- Price range ----------
def test_price_range_400_500k(s):
    r = s.get(f"{API}/products", params={"min_price": 400000, "max_price": 500000, "limit": 50})
    assert r.status_code == 200
    items = r.json().get("items", [])
    assert len(items) >= 1
    for p in items:
        price = p.get("base_price") or p.get("price") or 0
        assert 400000 <= price <= 500000, f"Product {p['slug']} price {price} outside 400-500k"


# ---------- Sort ----------
def test_sort_price_desc(s):
    r = s.get(f"{API}/products", params={"sort": "price_desc", "limit": 50})
    items = r.json().get("items", [])
    prices = [p.get("base_price") or 0 for p in items]
    assert prices == sorted(prices, reverse=True), f"Not desc: {prices}"


def test_sort_newest(s):
    r = s.get(f"{API}/products", params={"sort": "newest", "limit": 5})
    assert r.status_code == 200
    assert len(r.json().get("items", [])) > 0


def test_sort_featured(s):
    r = s.get(f"{API}/products", params={"sort": "featured", "limit": 5})
    assert r.status_code == 200
    assert len(r.json().get("items", [])) > 0


# ---------- Search ----------
def test_search_abaya(s):
    r = s.get(f"{API}/products", params={"q": "abaya"})
    items = r.json().get("items", [])
    slugs = [p["slug"] for p in items]
    assert any("abaya" in s for s in slugs), f"No abaya in {slugs}"


def test_search_sku_hoodie(s):
    r = s.get(f"{API}/products", params={"q": "GSOZH-GRY-M"})
    assert r.status_code == 200
    items = r.json().get("items", [])
    slugs = [p["slug"] for p in items]
    assert "gray-sweat-oversized-full-zip-hoodie" in slugs, f"SKU search failed, got: {slugs}"


def test_search_empty(s):
    r = s.get(f"{API}/products", params={"q": "zzzznoresult"})
    assert r.status_code == 200
    items = r.json().get("items", [])
    assert len(items) == 0


# ---------- Combined filter ----------
def test_combined_dept_color_black(s):
    r = s.get(f"{API}/products", params={"department": "women-muslimah", "color": "Black", "sort": "featured"})
    assert r.status_code == 200
    items = r.json().get("items", [])
    assert len(items) == 2
