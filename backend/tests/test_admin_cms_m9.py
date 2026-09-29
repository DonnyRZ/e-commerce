"""Milestone 9 — Admin Core + CMS tests (single-vendor operator).

Covers: admin RBAC, dashboard, product/category CRUD, order payment gate,
payment review notes, CMS draft/publish/archive safety (drafts never leak
to the public API), preview tokens, content sanitization, revisions,
media upload validation, audit log.
"""
import base64
from io import BytesIO
import os
import struct
import uuid
import zlib

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


def _unique_png(tag):
    chunk_type = b"tEXt"
    content = b"TestTag\x00" + tag.encode("ascii")
    chunk = (
        struct.pack(">I", len(content)) + chunk_type + content
        + struct.pack(">I", zlib.crc32(chunk_type + content) & 0xFFFFFFFF)
    )
    marker = PNG_1PX.rfind(b"\x00\x00\x00\x00IEND")
    return PNG_1PX[:marker] + chunk + PNG_1PX[marker:]


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
        "workflow_counts", "open_inquiries", "preorders_in_progress",
        "sales_total", "recent_orders", "payment_review_count", "payment_count",
    ):
        assert key in d, key
    assert set(d["workflow_counts"]) >= {
        "inquiry", "pending_payment", "payment_review", "paid",
        "supplier_shipping", "received_by_admin", "customer_shipping", "delivered",
        "payment",
    }
    assert d["payment_count"] == (
        d["workflow_counts"]["pending_payment"]
        + d["workflow_counts"]["payment_review"]
    )


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


def test_product_and_variant_delete_guards(admin, customer):
    categories = admin.get(f"{API}/admin/categories").json()
    cats = categories if isinstance(categories, list) else categories.get("items", [])
    cat = next(c for c in cats if c.get("kind") == "category" and c.get("is_active"))
    tag = uuid.uuid4().hex[:8].upper()
    created = admin.post(
        f"{API}/admin/products",
        json={
            "category_id": cat["id"],
            "product_type": "general",
            "brand": "MC Delete Test",
            "base_price": 99000,
            "status": "draft",
            "media": [{"url": "/media/delete-test.jpg"}],
            "translations": {"en": {"name": f"Delete Test {tag}"}},
            "variants": [
                {"sku": f"DEL-{tag}-A", "option_values": {"size": "S"}, "stock_quantity": 4},
                {"sku": f"DEL-{tag}-B", "option_values": {"size": "M"}, "stock_quantity": 4},
            ],
        },
    )
    assert created.status_code == 201, created.text
    product = created.json()
    product_id = product["id"]
    first_variant, last_variant = product["variants"]
    guest = requests.Session()

    try:
        assert customer.delete(
            f"{API}/admin/products/{product_id}",
            headers={"X-CSRF-Token": customer.cookies.get("csrf_token")},
        ).status_code == 403

        no_csrf = requests.Session()
        no_csrf.cookies.update(admin.cookies)
        assert no_csrf.delete(f"{API}/admin/products/{product_id}").status_code == 403

        deleted_variant = admin.delete(f"{API}/admin/variants/{first_variant['id']}")
        assert deleted_variant.status_code == 200, deleted_variant.text
        assert deleted_variant.json()["deleted"] is True

        last_variant_delete = admin.delete(f"{API}/admin/variants/{last_variant['id']}")
        assert last_variant_delete.status_code == 409
        assert last_variant_delete.json()["detail"]["error"] == "last_variant"

        activated = admin.patch(
            f"{API}/admin/products/{product_id}",
            json={"status": "active"},
        )
        assert activated.status_code == 200, activated.text

        cart_add = guest.post(
            f"{API}/cart/items",
            json={
                "product_id": product_id,
                "variant_id": last_variant["id"],
                "quantity": 1,
            },
        )
        assert cart_add.status_code == 201, cart_add.text

        active_delete = admin.delete(f"{API}/admin/products/{product_id}")
        assert active_delete.status_code == 409
        assert active_delete.json()["detail"]["error"] == "product_must_be_inactive"

        deactivated = admin.patch(
            f"{API}/admin/products/{product_id}",
            json={"status": "inactive"},
        )
        assert deactivated.status_code == 200, deactivated.text

        in_use_delete = admin.delete(f"{API}/admin/products/{product_id}")
        assert in_use_delete.status_code == 409
        in_use_detail = in_use_delete.json()["detail"]
        assert in_use_detail["error"] == "product_in_use"
        assert in_use_detail["references"]["cart_items"] == 1

        assert guest.delete(f"{API}/cart", params={"guest": "true"}).status_code == 204
        deleted_product = admin.delete(f"{API}/admin/products/{product_id}")
        assert deleted_product.status_code == 200, deleted_product.text
        assert deleted_product.json() == {"deleted": True, "product_id": product_id}
        assert admin.get(f"{API}/admin/products/{product_id}").status_code == 404

        audit = admin.get(f"{API}/admin/audit", params={"page_size": 100})
        assert audit.status_code == 200
        assert any(
            row["action"] == "admin.product.delete"
            and row["target_id"] == product_id
            for row in audit.json()["items"]
        )
    finally:
        guest.delete(f"{API}/cart", params={"guest": "true"})
        # The successful path above removes the product; this is only for an
        # assertion failure before the final delete.
        current = admin.get(f"{API}/admin/products/{product_id}")
        if current.status_code == 200:
            admin.patch(f"{API}/admin/products/{product_id}", json={"status": "inactive"})
            admin.delete(f"{API}/admin/products/{product_id}")


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


def test_taxonomy_department_category_crud_and_guards(admin, customer):
    """Exercise the full Catalog taxonomy flow through the real HTTP API."""

    tag = uuid.uuid4().hex[:10]
    department_slug = f"crud-department-{tag}"
    category_id = department_id = None

    # The endpoint must be protected by both admin RBAC and CSRF.
    assert customer.get(f"{API}/admin/categories").status_code == 403
    no_csrf = requests.Session()
    no_csrf.cookies.update(admin.cookies)
    assert no_csrf.post(
        f"{API}/admin/categories",
        json={
            "slug": department_slug,
            "department": department_slug,
            "kind": "department",
            "translations": {"en": {"name": "No CSRF Department"}},
        },
    ).status_code == 403

    try:
        created_department = admin.post(
            f"{API}/admin/categories",
            json={
                "slug": department_slug,
                "department": department_slug,
                "kind": "department",
                "is_active": False,
                "translations": {
                    "en": {"name": f"CRUD Department {tag}"},
                    "id": {"name": f"Departemen CRUD {tag}"},
                },
            },
        )
        assert created_department.status_code == 201, created_department.text
        department = created_department.json()
        department_id = department["id"]
        assert department["kind"] == "department"
        assert department["parent_id"] is None
        assert department["is_active"] is False

        activated_department = admin.patch(
            f"{API}/admin/categories/{department_id}",
            json={"is_active": True, "sort_order": 7},
        )
        assert activated_department.status_code == 200, activated_department.text
        assert activated_department.json()["is_active"] is True
        assert activated_department.json()["sort_order"] == 7

        created_category = admin.post(
            f"{API}/admin/categories",
            json={
                "slug": f"{department_slug}-category",
                "department": department_slug,
                "kind": "category",
                "parent_id": department_id,
                "translations": {"en": {"name": f"CRUD Category {tag}"}},
            },
        )
        assert created_category.status_code == 201, created_category.text
        category = created_category.json()
        category_id = category["id"]
        assert category["kind"] == "category"
        assert category["parent_id"] == department_id
        assert category["is_active"] is False
        assert category["is_leaf"] is True

        activated_category = admin.patch(
            f"{API}/admin/categories/{category_id}",
            json={"is_active": True, "sort_order": 3},
        )
        assert activated_category.status_code == 200, activated_category.text
        assert activated_category.json()["is_active"] is True

        # Active descendants prevent deactivating a parent, and children prevent
        # deleting a department. These are the safeguards the Catalog UI relies on.
        blocked_deactivate = admin.patch(
            f"{API}/admin/categories/{department_id}",
            json={"is_active": False},
        )
        assert blocked_deactivate.status_code == 400
        assert blocked_deactivate.json()["detail"]["error"] == "active_children_present"

        assert admin.patch(
            f"{API}/admin/categories/{category_id}",
            json={"is_active": False},
        ).status_code == 200
        assert admin.delete(f"{API}/admin/categories/{department_id}").status_code == 409
        blocked_delete = admin.delete(f"{API}/admin/categories/{department_id}")
        assert blocked_delete.status_code == 409
        assert blocked_delete.json()["detail"]["error"] == "category_in_use"
        assert blocked_delete.json()["detail"]["children"] == 1

        assert admin.delete(f"{API}/admin/categories/{category_id}").status_code in (200, 204)
        assert admin.delete(f"{API}/admin/categories/{department_id}").status_code in (200, 204)
    finally:
        # Cleanup is deliberately idempotent so a failed assertion cannot leave
        # taxonomy nodes in the local verification database.
        for node_id in (category_id, department_id):
            if node_id:
                admin.delete(f"{API}/admin/categories/{node_id}")


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
        json={"note": "Historical payment record reviewed — amounts match."},
    )
    assert r.status_code == 200, r.text
    assert r.json()["review_note"].startswith("Historical")


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


def test_cms_crud_for_every_content_type(admin):
    """Every CMS type can be created, edited, listed, archived and removed."""
    tag = uuid.uuid4().hex[:10]
    types = (
        "hero", "announcement", "banner", "story", "page", "faq_item",
        "nav_item", "footer_group", "footer_item", "footer_text",
        "homepage_section", "department_visual",
    )
    created_ids = []
    footer_group_slug = f"footer-{tag}"
    footer_group_id = None
    try:
        for content_type in types:
            internal_name = f"CMS {content_type} {tag}"
            slug = "" if content_type in ("homepage_section", "department_visual") else f"{content_type}-{tag}"
            translations = {
                "en": {
                    "title": f"{content_type} {tag}",
                    "alt_text": f"{content_type} image {tag}",
                }
            }
            payload = {}
            if content_type == "footer_item":
                payload["group"] = footer_group_slug
            body = {
                "content_type": content_type,
                "internal_name": internal_name,
                "slug": slug,
                "placement": "home_stories" if content_type == "footer_text" else "",
                "payload": payload,
                "translations": translations,
            }
            response = admin.post(f"{API}/admin/cms/content", json=body)
            assert response.status_code == 201, f"{content_type}: {response.status_code} {response.text}"
            entry = response.json()
            created_ids.append(entry["id"])
            if content_type == "footer_group":
                footer_group_slug = entry["slug"]
                footer_group_id = entry["id"]
            if content_type == "footer_item":
                renamed_group = admin.patch(
                    f"{API}/admin/cms/content/{footer_group_id}",
                    json={"slug": f"renamed-{tag}"},
                )
                assert renamed_group.status_code == 409
                assert renamed_group.json()["detail"]["error"] == "footer_group_in_use"

            listed = admin.get(
                f"{API}/admin/cms/content",
                params={"type": content_type, "q": tag, "page": 1, "page_size": 10},
            )
            assert listed.status_code == 200 and any(item["id"] == entry["id"] for item in listed.json()["items"])

            updated = admin.patch(
                f"{API}/admin/cms/content/{entry['id']}",
                json={"internal_name": f"{internal_name} edited"},
            )
            assert updated.status_code == 200, f"{content_type}: {updated.status_code} {updated.text}"
            assert admin.get(f"{API}/admin/cms/content/{entry['id']}").json()["internal_name"].endswith("edited")
    finally:
        # Delete children before their footer group, preserving test data safety
        # even if an assertion fails partway through the type matrix.
        for entry_id in reversed(created_ids):
            current = admin.get(f"{API}/admin/cms/content/{entry_id}")
            if current.status_code != 200:
                continue
            if current.json()["status"] != "archived":
                admin.post(f"{API}/admin/cms/content/{entry_id}/status", json={"action": "archive"})
            admin.delete(f"{API}/admin/cms/content/{entry_id}")


def test_published_cms_edits_are_staged_until_publish(admin):
    slug = f"staged-{uuid.uuid4().hex[:10]}"
    created = admin.post(
        f"{API}/admin/cms/content",
        json={
            "content_type": "page",
            "internal_name": f"Staged page {slug}",
            "slug": slug,
            "translations": {"en": {"title": "Live title", "body": "Live body"}},
        },
    )
    assert created.status_code == 201, created.text
    entry_id = created.json()["id"]
    try:
        r = admin.post(f"{API}/admin/cms/content/{entry_id}/status", json={"action": "publish"})
        assert r.status_code == 200, r.text
        assert requests.get(f"{API}/cms/public/pages/{slug}").json()["translations"]["en"]["title"] == "Live title"

        r = admin.patch(
            f"{API}/admin/cms/content/{entry_id}",
            json={"translations": {"en": {"title": "Draft title", "body": "Draft body"}}},
        )
        assert r.status_code == 200, r.text
        detail = r.json()
        assert detail["status"] == "published"
        assert detail["has_unpublished_changes"] is True
        assert detail["translations"]["en"]["title"] == "Live title"
        assert detail["working_copy"]["translations"]["en"]["title"] == "Draft title"
        assert requests.get(f"{API}/cms/public/pages/{slug}").json()["translations"]["en"]["title"] == "Live title"
        listed = admin.get(f"{API}/admin/cms/content", params={"q": slug}).json()
        assert next(item for item in listed["items"] if item["id"] == entry_id)["has_unpublished_changes"] is True

        token = admin.post(f"{API}/admin/cms/content/{entry_id}/preview-token").json()
        preview = requests.get(f"{BASE}{token['preview_url']}")
        assert preview.status_code == 200
        assert preview.json()["translations"]["en"]["title"] == "Draft title"

        revisions = admin.get(f"{API}/admin/cms/content/{entry_id}/revisions").json()
        published_revision = next(revision for revision in revisions if revision["action"] == "published")
        restored = admin.post(
            f"{API}/admin/cms/content/{entry_id}/restore/{published_revision['id']}"
        )
        assert restored.status_code == 200, restored.text
        assert restored.json()["has_unpublished_changes"] is True
        assert restored.json()["working_copy"]["translations"]["en"]["title"] == "Live title"
        assert requests.get(f"{API}/cms/public/pages/{slug}").json()["translations"]["en"]["title"] == "Live title"

        r = admin.patch(
            f"{API}/admin/cms/content/{entry_id}",
            json={"translations": {"en": {"title": "Draft title", "body": "Draft body"}}},
        )
        assert r.status_code == 200, r.text

        r = admin.post(f"{API}/admin/cms/content/{entry_id}/status", json={"action": "publish"})
        assert r.status_code == 200, r.text
        assert r.json()["has_unpublished_changes"] is False
        assert requests.get(f"{API}/cms/public/pages/{slug}").json()["translations"]["en"]["title"] == "Draft title"

        assert admin.delete(f"{API}/admin/cms/content/{entry_id}").status_code == 409
    finally:
        current = admin.get(f"{API}/admin/cms/content/{entry_id}")
        if current.status_code == 200:
            if current.json()["status"] != "archived":
                admin.post(f"{API}/admin/cms/content/{entry_id}/status", json={"action": "archive"})
            admin.delete(f"{API}/admin/cms/content/{entry_id}")


def test_publish_requires_english_content_and_delete_requires_archive(admin):
    created = admin.post(
        f"{API}/admin/cms/content",
        json={
            "content_type": "banner",
            "internal_name": f"Incomplete banner {uuid.uuid4().hex[:8]}",
            "translations": {"id": {"title": "Banner Indonesia"}},
        },
    )
    assert created.status_code == 201, created.text
    entry_id = created.json()["id"]
    try:
        r = admin.post(f"{API}/admin/cms/content/{entry_id}/status", json={"action": "publish"})
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "incomplete_english"
        assert admin.delete(f"{API}/admin/cms/content/{entry_id}").status_code == 409
    finally:
        current = admin.get(f"{API}/admin/cms/content/{entry_id}")
        if current.status_code == 200:
            if current.json()["status"] != "archived":
                admin.post(f"{API}/admin/cms/content/{entry_id}/status", json={"action": "archive"})
            admin.delete(f"{API}/admin/cms/content/{entry_id}")


def test_cms_validates_relations_sections_and_duplicate_slugs(admin):
    tag = uuid.uuid4().hex[:10]
    invalid_cases = (
        {
            "content_type": "footer_item",
            "slug": f"footer-item-{tag}",
            "cta_url": "/shop",
            "payload": {"group": f"missing-{tag}"},
            "expected": "invalid_footer_group",
        },
        {
            "content_type": "homepage_section",
            "slug": f"unknown-{tag}",
            "expected": "invalid_homepage_section",
        },
        {
            "content_type": "department_visual",
            "slug": f"unknown-department-{tag}",
            "expected": "invalid_department",
        },
    )
    for case in invalid_cases:
        response = admin.post(
            f"{API}/admin/cms/content",
            json={
                "content_type": case["content_type"],
                "internal_name": f"Invalid relation {tag}",
                "slug": case["slug"],
                "cta_url": case.get("cta_url"),
                "payload": case.get("payload", {}),
                "translations": {"en": {"title": "Invalid relation"}},
            },
        )
        assert response.status_code == 400, response.text
        assert response.json()["detail"]["error"] == case["expected"]

    slug = f"duplicate-{tag}"
    first = admin.post(
        f"{API}/admin/cms/content",
        json={
            "content_type": "banner",
            "internal_name": f"Duplicate test {tag}",
            "slug": slug,
            "translations": {"en": {"title": "Duplicate test"}},
        },
    )
    assert first.status_code == 201, first.text
    entry_id = first.json()["id"]
    try:
        second = admin.post(
            f"{API}/admin/cms/content",
            json={
                "content_type": "banner",
                "internal_name": f"Duplicate second {tag}",
                "slug": slug,
                "translations": {"en": {"title": "Duplicate test"}},
            },
        )
        assert second.status_code == 409
        assert second.json()["detail"]["error"] == "duplicate_slug"
    finally:
        current = admin.get(f"{API}/admin/cms/content/{entry_id}")
        if current.status_code == 200:
            if current.json()["status"] != "archived":
                admin.post(f"{API}/admin/cms/content/{entry_id}/status", json={"action": "archive"})
            admin.delete(f"{API}/admin/cms/content/{entry_id}")


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
        files={"file": ("oversize.png", b"x" * (25 * 1024 * 1024 + 1), "image/png")},
    )
    assert r.status_code == 413
    assert r.json()["detail"]["error"] == "file_too_large"

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

    variant = requests.get(f"{BASE}{asset['url']}", params={"width": 640, "format": "webp"})
    assert variant.status_code == 200
    assert variant.headers["Content-Type"].startswith("image/webp")
    assert variant.headers["Cache-Control"] == "public, max-age=31536000, immutable"
    from PIL import Image

    with Image.open(BytesIO(variant.content)) as optimized:
        assert optimized.size == (1, 1)

    invalid_variant = requests.get(f"{BASE}{asset['url']}", params={"width": 777, "format": "webp"})
    assert invalid_variant.status_code == 422

    r = admin.patch(
        f"{API}/admin/cms/media/{asset['id']}",
        json={"translations": {"en": {"alt_text": "pixel", "caption": "Caption retained"}}},
    )
    assert r.status_code == 200
    r = admin.patch(
        f"{API}/admin/cms/media/{asset['id']}",
        json={"translations": {"en": {"alt_text": "updated pixel"}}},
    )
    assert r.status_code == 200
    assert r.json()["translations"]["en"]["caption"] == "Caption retained"
    assert r.json()["translations"]["en"]["alt_text"] == "updated pixel"

    r = admin.delete(f"{API}/admin/cms/media/{asset['id']}")
    assert r.status_code in (200, 204), r.text


def test_media_in_use_cannot_be_deleted(admin):
    tag = uuid.uuid4().hex
    uploaded = admin.post(
        f"{API}/admin/cms/media",
        files={"file": (f"used-{tag[:8]}.png", _unique_png(tag), "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    asset = uploaded.json()
    entry_id = None
    try:
        created = admin.post(
            f"{API}/admin/cms/content",
            json={
                "content_type": "banner",
                "internal_name": f"Media reference {uuid.uuid4().hex[:8]}",
                "media_id": asset["id"],
                "translations": {"en": {"title": "Referenced banner"}},
            },
        )
        assert created.status_code == 201, created.text
        entry_id = created.json()["id"]
        current_media = admin.get(f"{API}/admin/cms/media", params={"q": asset["original_filename"]})
        current_asset = next(item for item in current_media.json()["items"] if item["id"] == asset["id"])
        assert current_asset["usage_count"] >= 1
        blocked = admin.delete(f"{API}/admin/cms/media/{asset['id']}")
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["error"] == "media_in_use"
    finally:
        if entry_id:
            current = admin.get(f"{API}/admin/cms/content/{entry_id}")
            if current.status_code == 200:
                if current.json()["status"] != "archived":
                    admin.post(f"{API}/admin/cms/content/{entry_id}/status", json={"action": "archive"})
                admin.delete(f"{API}/admin/cms/content/{entry_id}")
        admin.delete(f"{API}/admin/cms/media/{asset['id']}")


# ------------------------------ audit ----------------------------------------


def test_audit_records_admin_actions(admin):
    r = admin.get(f"{API}/admin/audit", params={"page_size": 50})
    assert r.status_code == 200
    actions = {i["action"] for i in r.json()["items"]}
    assert any(a.startswith(("cms.", "admin.")) for a in actions)
