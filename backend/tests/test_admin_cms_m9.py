"""Milestone 9 — Admin Core + CMS tests (single-vendor operator).

Covers: admin RBAC, dashboard, product/category CRUD, order payment gate,
payment review notes, CMS draft/publish/archive safety (drafts never leak
to the public API), preview tokens, content sanitization, revisions,
media upload validation, audit log.
"""
import base64
import os
import uuid

import pytest
import requests

BASE = os.environ.get(
    "REACT_APP_BACKEND_URL", "http://127.0.0.1:8000"
).rstrip("/")
API = f"{BASE}/api/v1"

ADMIN = ("bmulyanto@gmail.com", "MC-Adm1n-7f3k29xQ-2026")
CUSTOMER = ("customer.demo@muslimahcantik.id", "MC-Cust0mer-9d2m48Lw-2026")

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    s.headers["X-CSRF-Token"] = s.cookies.get("csrf_token")
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def customer():
    return _login(*CUSTOMER)


# ------------------------------ RBAC ---------------------------------------


def test_rbac_blocks_customer(customer):
    assert customer.get(f"{API}/admin/dashboard").status_code == 403
    assert customer.get(f"{API}/admin/cms/content").status_code == 403
    assert customer.get(f"{API}/admin/payments/review").status_code == 403


def test_rbac_blocks_anonymous():
    assert requests.get(f"{API}/admin/dashboard").status_code == 401


# ------------------------------ dashboard / settings ------------------------


def test_dashboard_shape(admin):
    r = admin.get(f"{API}/admin/dashboard")
    assert r.status_code == 200
    d = r.json()
    for key in (
        "total_products", "active_products", "orders_by_status",
        "sales_total", "recent_orders", "payment_review_count",
    ):
        assert key in d, key


def test_settings_single_vendor(admin):
    r = admin.get(f"{API}/admin/settings")
    assert r.status_code == 200
    s = r.json()
    assert s["business_model"] == "single_vendor"
    assert sorted(s["locales"]) == ["en", "id", "ru", "uz"]


# ------------------------------ products / categories -----------------------


def test_products_list_and_inventory_filter(admin):
    r = admin.get(f"{API}/admin/products", params={"page": 1, "page_size": 10})
    assert r.status_code == 200
    items = r.json()["items"]
    assert items
    for key in ("id", "slug", "name", "status", "variant_count", "total_stock", "stock_state"):
        assert key in items[0], key
    r = admin.get(f"{API}/admin/products", params={"inventory": "out_of_stock"})
    assert r.status_code == 200
    assert all(i["stock_state"] == "out_of_stock" for i in r.json()["items"])


def test_product_crud_flow(admin):
    r = admin.get(f"{API}/admin/categories")
    assert r.status_code == 200
    data = r.json()
    cats = data if isinstance(data, list) else data.get("items", [])
    cat = next(c for c in cats if c.get("kind") != "department")
    tag = uuid.uuid4().hex[:8].upper()
    payload = {
        "category_id": cat["id"],
        "product_type": "general",
        "brand": "MC Test",
        "base_price": 99000,
        "status": "draft",
        "media": [{"url": "/media/test-fixture.jpg"}],
        "translations": {
            "en": {"name": f"Admin Test Product {tag}"},
            "id": {"name": f"Produk Uji {tag}"},
        },
        "variants": [{"sku": f"ADM-{tag}", "option_values": {"size": "One"}, "stock_quantity": 4}],
    }
    r = admin.post(f"{API}/admin/products", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    pid, vid = body["id"], body["variants"][0]["id"]

    r = admin.patch(f"{API}/admin/products/{pid}", json={"base_price": 109000, "status": "active"})
    assert r.status_code == 200 and r.json()["base_price"] == 109000

    r = admin.patch(f"{API}/admin/variants/{vid}/inventory", json={"stock_quantity": 7})
    assert r.status_code == 200 and r.json()["stock_quantity"] == 7

    r = admin.get(f"{API}/admin/products", params={"q": tag})
    assert r.json()["total"] >= 1

    # cleanup — keep test product out of the storefront
    r = admin.patch(f"{API}/admin/products/{pid}", json={"status": "inactive"})
    assert r.status_code == 200


def test_categories_crud(admin):
    tag = uuid.uuid4().hex[:8]
    r = admin.post(
        f"{API}/admin/categories",
        json={
            "slug": f"admin-test-{tag}",
            "department": "tropical-halal-skincare",
            "sort_order": 99,
            "translations": {"en": {"name": f"Test Cat {tag}"}, "id": {"name": f"Kategori Uji {tag}"}},
        },
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    r = admin.patch(f"{API}/admin/categories/{cid}", json={"sort_order": 100})
    assert r.status_code == 200 and r.json()["sort_order"] == 100
    r = admin.delete(f"{API}/admin/categories/{cid}")
    assert r.status_code in (200, 204), r.text


# ------------------------------ orders / customers --------------------------


def test_orders_list_detail_and_payment_gate(admin):
    r = admin.get(f"{API}/admin/orders", params={"payment_state": "unpaid"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert items, "expected unpaid orders from seed"
    num = items[0]["order_number"]
    r = admin.get(f"{API}/admin/orders/{num}")
    assert r.status_code == 200 and r.json()["order_number"] == num
    # unpaid orders must never move into fulfillment
    r = admin.patch(f"{API}/admin/orders/{num}/status", json={"status": "processing"})
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "payment_not_eligible"


def test_customers_list_and_detail(admin):
    r = admin.get(f"{API}/admin/customers", params={"q": "customer.demo"})
    assert r.status_code == 200 and r.json()["total"] >= 1
    cid = r.json()["items"][0]["id"]
    r = admin.get(f"{API}/admin/customers/{cid}")
    assert r.status_code == 200 and "orders" in r.json()


# ------------------------------ payment review ------------------------------


def test_payment_review_note(admin):
    r = admin.get(f"{API}/admin/payments/review")
    assert r.status_code == 200
    items = r.json()["items"]
    if not items:
        pytest.skip("review queue empty")
    pid = items[0]["payment_id"]
    r = admin.post(
        f"{API}/admin/payments/{pid}/review-note",
        json={"note": "Checked against CLICK dashboard — amounts match."},
    )
    assert r.status_code == 200, r.text
    assert r.json()["review_note"].startswith("Checked")


# ------------------------------ CMS workflow ---------------------------------


def test_cms_draft_never_leaks(admin):
    tag = uuid.uuid4().hex[:8]
    slug = f"test-page-{tag}"
    r = admin.post(
        f"{API}/admin/cms/content",
        json={
            "content_type": "page",
            "internal_name": f"Test page {tag}",
            "slug": slug,
            "translations": {"en": {"title": "Secret draft", "body": "draft body"}},
        },
    )
    assert r.status_code == 201, r.text
    entry = r.json()
    assert entry["status"] == "draft"

    # draft invisible to the public API
    assert requests.get(f"{API}/cms/public/pages/{slug}").status_code == 404

    r = admin.post(f"{API}/admin/cms/content/{entry['id']}/status", json={"action": "publish"})
    assert r.status_code == 200 and r.json()["status"] == "published"
    pub = requests.get(f"{API}/cms/public/pages/{slug}")
    assert pub.status_code == 200
    assert pub.json()["translations"]["en"]["title"] == "Secret draft"

    r = admin.post(f"{API}/admin/cms/content/{entry['id']}/status", json={"action": "unpublish"})
    assert r.status_code == 200
    assert requests.get(f"{API}/cms/public/pages/{slug}").status_code == 404

    # invalid transition: draft -> unpublish
    r = admin.post(f"{API}/admin/cms/content/{entry['id']}/status", json={"action": "unpublish"})
    assert r.status_code == 400

    r = admin.post(f"{API}/admin/cms/content/{entry['id']}/status", json={"action": "archive"})
    assert r.status_code == 200 and r.json()["status"] == "archived"


def test_cms_preview_token(admin):
    r = admin.post(
        f"{API}/admin/cms/content",
        json={
            "content_type": "banner",
            "internal_name": f"Preview {uuid.uuid4().hex[:6]}",
            "translations": {"en": {"title": "Preview me"}},
        },
    )
    assert r.status_code == 201, r.text
    entry = r.json()
    r = admin.post(f"{API}/admin/cms/content/{entry['id']}/preview-token")
    assert r.status_code == 200
    pub = requests.get(f"{BASE}{r.json()['preview_url']}")  # no auth required
    assert pub.status_code == 200
    assert pub.json()["translations"]["en"]["title"] == "Preview me"
    admin.post(f"{API}/admin/cms/content/{entry['id']}/status", json={"action": "archive"})


def test_cms_content_safety(admin):
    r = admin.post(
        f"{API}/admin/cms/content",
        json={"content_type": "banner", "internal_name": "x", "cta_url": "javascript:alert(1)"},
    )
    assert r.status_code == 400 and r.json()["detail"]["error"] == "invalid_url"
    r = admin.post(
        f"{API}/admin/cms/content",
        json={
            "content_type": "banner",
            "internal_name": "x",
            "translations": {"en": {"title": "<script>alert(1)</script>"}},
        },
    )
    assert r.status_code == 400 and r.json()["detail"]["error"] == "unsafe_content"
    r = admin.post(
        f"{API}/admin/cms/content",
        json={
            "content_type": "banner",
            "internal_name": "x",
            "translations": {"fr": {"title": "wrong locale"}},
        },
    )
    assert r.status_code == 400 and r.json()["detail"]["error"] == "invalid_locale"


def test_cms_revision_restore(admin):
    r = admin.post(
        f"{API}/admin/cms/content",
        json={
            "content_type": "story",
            "internal_name": f"Rev {uuid.uuid4().hex[:6]}",
            "translations": {"en": {"title": "V1 title"}},
        },
    )
    assert r.status_code == 201, r.text
    entry = r.json()
    r = admin.patch(
        f"{API}/admin/cms/content/{entry['id']}",
        json={"translations": {"en": {"title": "V2 title"}}},
    )
    assert r.status_code == 200
    revs = admin.get(f"{API}/admin/cms/content/{entry['id']}/revisions").json()
    assert len(revs) >= 2
    r = admin.post(f"{API}/admin/cms/content/{entry['id']}/restore/{revs[-1]['id']}")
    assert r.status_code == 200
    assert r.json()["translations"]["en"]["title"] == "V1 title"
    assert r.json()["status"] == "draft"
    admin.post(f"{API}/admin/cms/content/{entry['id']}/status", json={"action": "archive"})


# ------------------------------ media ----------------------------------------


def test_media_upload_validation_and_serving(admin):
    r = admin.post(
        f"{API}/admin/cms/media",
        files={"file": ("evil.png", b"not an image", "image/png")},
    )
    assert r.status_code == 415

    r = admin.post(
        f"{API}/admin/cms/media",
        files={"file": ("pixel.png", PNG_1PX, "image/png")},
    )
    assert r.status_code == 201, r.text
    asset = r.json()
    assert asset["url"].startswith("/api/v1/cms/media/file/")

    f = requests.get(f"{BASE}{asset['url']}")
    assert f.status_code == 200
    assert f.headers["Content-Type"].startswith("image/png")

    r = admin.patch(
        f"{API}/admin/cms/media/{asset['id']}",
        json={"translations": {"en": {"alt_text": "pixel", "caption": ""}}},
    )
    assert r.status_code == 200

    r = admin.delete(f"{API}/admin/cms/media/{asset['id']}")
    assert r.status_code in (200, 204), r.text


# ------------------------------ audit ----------------------------------------


def test_audit_records_admin_actions(admin):
    r = admin.get(f"{API}/admin/audit", params={"page_size": 50})
    assert r.status_code == 200
    actions = {i["action"] for i in r.json()["items"]}
    assert any(a.startswith(("cms.", "admin.")) for a in actions)
