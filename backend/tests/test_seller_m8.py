"""Milestone 8 — Seller Marketplace tests.

Isolation is verified through the BACKEND API (never UI hiding):
Seller A = partner-uniqlo (apparel), Seller B = tropicalglow (skincare).
"""
import os, subprocess, uuid, requests, pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
API = f"{BASE}/api/v1"
DB_URL = "postgresql://muslimah:muslimah_dev_pass@localhost:5432/muslimah_cantik"

SELLER_A = ("partner-uniqlo@muslimahcantik.id", "MC-S3ller-5t8r31Vn-2026")
SELLER_B = ("tropicalglow@muslimahcantik.id", "MC-S3llerB-9w4k72Pz-2026")
CUSTOMER = ("customer.demo@muslimahcantik.id", "MC-Cust0mer-9d2m48Lw-2026")

ADDR = {
    "recipient_name": "Test User", "phone": "+998901112233",
    "address_line_1": "1 Test Street", "city": "Tashkent",
    "state_province": "Tashkent", "postal_code": "100000", "country_code": "UZ",
}


def _psql(sql):
    out = subprocess.run(["psql", DB_URL, "-tA", "-c", sql], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    s.headers["X-CSRF-Token"] = s.cookies.get("csrf_token")
    return s


@pytest.fixture(scope="module")
def seller_a():
    return _login(*SELLER_A)


@pytest.fixture(scope="module")
def seller_b():
    return _login(*SELLER_B)


def _product(slug):
    r = requests.get(f"{API}/catalog/products/{slug}")
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def a_product():
    return _product("gray-sweat-oversized-full-zip-hoodie")  # uniqlo (A)


@pytest.fixture(scope="module")
def b_product():
    return _product("brightening-serum-30ml")  # tropicalglow (B)


def _paid_multiseller_order(a_product, b_product):
    """Customer checkout with items from BOTH sellers, paid via mock."""
    s = _login(*CUSTOMER)
    s.delete(f"{API}/cart")
    a_var = next(v for v in a_product["variants"] if v["sku"] == "GSOZH-BGE-M")
    b_var = b_product["variants"][0]
    for prod, var in ((a_product, a_var), (b_product, b_var)):
        r = s.post(f"{API}/cart/items", json={
            "product_id": prod["id"], "variant_id": var["id"], "quantity": 1,
        })
        assert r.status_code == 201, r.text
    r = s.post(f"{API}/checkout/orders", json={
        "idempotency_key": uuid.uuid4().hex, "shipping_method": "standard",
        "locale": "en", "address": ADDR,
    })
    assert r.status_code == 201, r.text
    order = r.json()
    pay = s.post(f"{API}/payments/mock/pay", json={
        "merchant_trans_id": order["payment"]["merchant_trans_id"],
        "order_number": order["order_number"], "scenario": "SUCCESS",
    })
    assert pay.json()["payment_status"] == "paid", pay.text
    return s, order


# ---------------- RBAC ----------------

def test_customer_and_guest_blocked_from_seller_api():
    c = _login(*CUSTOMER)
    assert c.get(f"{API}/seller/dashboard").status_code == 403
    assert c.get(f"{API}/seller/products").status_code == 403
    g = requests.Session()
    assert g.get(f"{API}/seller/dashboard").status_code == 401
    assert g.get(f"{API}/seller/orders").status_code == 401


def test_admin_not_seller():
    admin = _login("bmulyanto@gmail.com", "MC-Adm1n-7f3k29xQ-2026")
    # seller namespace is seller-scoped; admin dashboard comes in Admin Core
    assert admin.get(f"{API}/seller/dashboard").status_code == 403


# ---------------- dashboard / profile ----------------

def test_dashboard_shape(seller_a):
    r = seller_a.get(f"{API}/seller/dashboard")
    assert r.status_code == 200
    j = r.json()
    for key in ("active_products", "low_stock_variants", "out_of_stock_variants",
                "pending_fulfillments", "sales_total", "currency", "recent_orders"):
        assert key in j
    assert j["currency"] == "UZS"
    assert j["active_products"] >= 1


def test_profile_get_and_patch(seller_a, seller_b):
    r = seller_a.get(f"{API}/seller/profile")
    assert r.status_code == 200
    before = r.json()
    assert before["store_name"]
    r2 = seller_a.patch(f"{API}/seller/profile", json={
        "store_name": "UNIQLO Products Partner",
        "description": "Official UNIQLO partner store.",
        "contact_phone": "+998901234500",
    })
    assert r2.status_code == 200
    assert r2.json()["contact_phone"] == "+998901234500"
    # seller B profile unaffected by A's edit
    b = seller_b.get(f"{API}/seller/profile").json()
    assert b["store_name"] != "UNIQLO Products Partner" or b["slug"] != r2.json()["slug"]
    # restore
    seller_a.patch(f"{API}/seller/profile", json={"store_name": before["store_name"],
                                                  "description": before.get("description"),
                                                  "contact_phone": before.get("contact_phone")})


# ---------------- product isolation ----------------

def test_product_lists_are_partitioned(seller_a, seller_b, a_product, b_product):
    a_items = seller_a.get(f"{API}/seller/products", params={"page_size": 50}).json()["items"]
    b_items = seller_b.get(f"{API}/seller/products", params={"page_size": 50}).json()["items"]
    a_ids = {p["id"] for p in a_items}
    b_ids = {p["id"] for p in b_items}
    assert a_product["id"] in a_ids and b_product["id"] in b_ids
    assert not (a_ids & b_ids), "seller lists must be disjoint"


def test_cross_seller_product_attacks_fail(seller_a, seller_b, a_product, b_product):
    b_var = b_product["variants"][0]
    a_var = next(v for v in a_product["variants"] if v["sku"] == "GSOZH-BGE-M")
    # A reads/edits/archives B product
    assert seller_a.get(f"{API}/seller/products/{b_product['id']}").status_code == 404
    assert seller_a.patch(f"{API}/seller/products/{b_product['id']}", json={"brand": "HACKED"}).status_code == 404
    assert seller_a.patch(f"{API}/seller/products/{b_product['id']}", json={"status": "inactive"}).status_code == 404
    # A edits B variant / inventory
    assert seller_a.patch(f"{API}/seller/variants/{b_var['id']}", json={"price_override": 1}).status_code == 404
    assert seller_a.patch(f"{API}/seller/variants/{b_var['id']}/inventory", json={"stock_quantity": 0}).status_code == 404
    # B performs equivalent attacks against A
    assert seller_b.get(f"{API}/seller/products/{a_product['id']}").status_code == 404
    assert seller_b.patch(f"{API}/seller/products/{a_product['id']}", json={"base_price": 1}).status_code == 404
    assert seller_b.patch(f"{API}/seller/variants/{a_var['id']}/inventory", json={"stock_quantity": 0}).status_code == 404
    # verify nothing changed
    assert _product("brightening-serum-30ml")["brand"] != "HACKED"


def test_seller_id_forgery_ignored(seller_a, seller_b):
    forged_seller_id = _psql("SELECT id FROM users WHERE email='tropicalglow@muslimahcantik.id'")
    sku = f"M8FORGE-{uuid.uuid4().hex[:6].upper()}"
    category_id = _psql("SELECT id FROM categories WHERE slug='sweaters-knitwear'")
    r = seller_a.post(f"{API}/seller/products", json={
        "category_id": category_id, "product_type": "apparel",
        "brand": "Forgery Test", "base_price": 100000, "status": "draft",
        "seller_id": forged_seller_id,  # must be ignored — extra field
        "translations": {"en": {"name": "Forgery Test Product"}},
        "variants": [{"sku": sku, "option_values": {"color": "Black", "size": "M"}, "stock_quantity": 3}],
    })
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert seller_a.get(f"{API}/seller/products/{pid}").status_code == 200
    assert seller_b.get(f"{API}/seller/products/{pid}").status_code == 404, "forged seller_id must not transfer ownership"
    owner = _psql(f"SELECT u.email FROM products p JOIN users u ON u.id=p.seller_id WHERE p.id='{pid}'")
    assert owner == SELLER_A[0]


# ---------------- product create / edit / archive ----------------

def _new_product_payload(sku_prefix):
    category_id = _psql("SELECT id FROM categories WHERE slug='sweaters-knitwear'")
    return {
        "category_id": category_id, "product_type": "apparel", "brand": "M8 Test",
        "base_price": 250000, "compare_at_price": 300000, "status": "draft",
        "attributes": {"material": "cotton"}, "tags": ["test"],
        "media": [{"url": "https://images.unsplash.com/photo-1434389677669-e08b4cac3105?w=800"}],
        "translations": {
            "en": {"name": f"M8 Test Hoodie {sku_prefix}", "short_description": "Test", "description": "Test desc"},
            "id": {"name": f"Hoodie Uji {sku_prefix}"},
            "uz": {"name": f"Test koylak {sku_prefix}"},
            "ru": {"name": f"Тестовое худи {sku_prefix}"},
        },
        "variants": [
            {"sku": f"{sku_prefix}-BLK-M", "option_values": {"color": "Black", "size": "M"}, "stock_quantity": 10},
            {"sku": f"{sku_prefix}-BLK-L", "option_values": {"color": "Black", "size": "L"}, "stock_quantity": 0,
             "price_override": 260000, "sale_price_override": 240000},
        ],
    }


@pytest.fixture(scope="module", autouse=True)
def _cleanup_test_products():
    yield
    _psql("DELETE FROM products WHERE slug LIKE 'm8%-%' OR slug LIKE 'forgery-test-%'")


def test_product_create_full_four_locales(seller_a):
    prefix = f"M8T{uuid.uuid4().hex[:5].upper()}"
    payload = {**_new_product_payload(prefix), "status": "active"}
    r = seller_a.post(f"{API}/seller/products", json=payload)
    assert r.status_code == 201, r.text
    j = r.json()
    try:
        assert set(j["translations"].keys()) == {"en", "id", "uz", "ru"}
        assert j["translations"]["id"]["name"].startswith("Hoodie Uji")
        assert len(j["variants"]) == 2
        assert j["status"] == "active"
        states = {v["sku"]: v["stock_state"] for v in j["variants"]}
        assert states[f"{prefix}-BLK-L"] == "out_of_stock"
        assert states[f"{prefix}-BLK-M"] == "in_stock"
        # storefront PDP renders the new product in all locales
        for loc, needle in (("id", "Hoodie Uji"), ("ru", "Тестовое худи")):
            p = requests.get(f"{API}/catalog/products/{j['slug']}", params={"locale": loc})
            assert p.status_code == 200 and needle in p.text
    finally:
        # archive immediately: active test products must not pollute the public catalog
        seller_a.patch(f"{API}/seller/products/{j['id']}", json={"status": "inactive"})


def test_product_create_validation(seller_a):
    payload = _new_product_payload(f"M8V{uuid.uuid4().hex[:5].upper()}")
    bad_category = {**payload, "category_id": "nonexistent123"}
    r = seller_a.post(f"{API}/seller/products", json=bad_category)
    assert r.status_code == 400 and r.json()["detail"]["error"] == "invalid_category"
    no_en = {**payload, "translations": {"id": {"name": "Hanya ID"}}}
    r2 = seller_a.post(f"{API}/seller/products", json=no_en)
    assert r2.status_code == 400 and r2.json()["detail"]["error"] == "translation_en_required"
    bad_locale = {**payload, "translations": {"en": {"name": "X"}, "fr": {"name": "Y"}}}
    r3 = seller_a.post(f"{API}/seller/products", json=bad_locale)
    assert r3.status_code == 400 and r3.json()["detail"]["error"] == "invalid_locale"
    neg_price = {**payload, "base_price": -100}
    assert seller_a.post(f"{API}/seller/products", json=neg_price).status_code == 422
    bad_status = {**payload, "status": "published"}
    assert seller_a.post(f"{API}/seller/products", json=bad_status).status_code == 400


def test_sku_uniqueness_conflict(seller_a, b_product):
    payload = _new_product_payload(f"M8S{uuid.uuid4().hex[:5].upper()}")
    payload["variants"] = [{"sku": b_product["variants"][0]["sku"], "option_values": {}, "stock_quantity": 1}]
    r = seller_a.post(f"{API}/seller/products", json=payload)
    assert r.status_code == 409 and r.json()["detail"]["error"] == "sku_exists"


def test_product_edit_and_archive(seller_a):
    prefix = f"M8E{uuid.uuid4().hex[:5].upper()}"
    created = seller_a.post(f"{API}/seller/products", json=_new_product_payload(prefix)).json()
    pid = created["id"]
    assert created["status"] == "draft"
    r = seller_a.patch(f"{API}/seller/products/{pid}", json={
        "brand": "M8 Edited", "translations": {"uz": {"name": "Tahrirlangan nom"}},
    })
    assert r.status_code == 200
    assert r.json()["brand"] == "M8 Edited"
    assert r.json()["translations"]["uz"]["name"] == "Tahrirlangan nom"
    assert r.json()["translations"]["en"]["name"].startswith("M8 Test Hoodie"), "untouched locale preserved"
    # publish → storefront serves it; archive → storefront stops serving it
    r_pub = seller_a.patch(f"{API}/seller/products/{pid}", json={"status": "active"})
    assert r_pub.status_code == 200 and r_pub.json()["status"] == "active"
    assert requests.get(f"{API}/catalog/products/{created['slug']}").status_code == 200
    r2 = seller_a.patch(f"{API}/seller/products/{pid}", json={"status": "inactive"})
    assert r2.status_code == 200 and r2.json()["status"] == "inactive"
    assert requests.get(f"{API}/catalog/products/{created['slug']}").status_code in (404, 410)
    # seller filters see it
    listed = seller_a.get(f"{API}/seller/products", params={"status": "inactive"}).json()["items"]
    assert any(p["id"] == pid for p in listed)


def test_flexible_variants_and_variant_crud(seller_a):
    prefix = f"M8F{uuid.uuid4().hex[:5].upper()}"
    payload = _new_product_payload(prefix)
    payload["variants"] = [
        {"sku": f"{prefix}-CRM-CRP", "option_values": {"color": "Cream", "material": "Crinkle"}, "stock_quantity": 4},
    ]
    created = seller_a.post(f"{API}/seller/products", json=payload)
    assert created.status_code == 201
    pid = created.json()["id"]
    # add a skincare-style {volume} variant
    r = seller_a.post(f"{API}/seller/products/{pid}/variants", json={
        "sku": f"{prefix}-VOL-50ML", "option_values": {"volume": "50 ml"}, "stock_quantity": 7,
    })
    assert r.status_code == 201, r.text
    variants = {v["sku"]: v for v in r.json()["variants"]}
    assert variants[f"{prefix}-VOL-50ML"]["option_values"] == {"volume": "50 ml"}
    # edit variant price; duplicate SKU rejected
    vid = variants[f"{prefix}-VOL-50ML"]["id"]
    r2 = seller_a.patch(f"{API}/seller/variants/{vid}", json={"price_override": 255000})
    assert r2.status_code == 200
    r3 = seller_a.patch(f"{API}/seller/variants/{vid}", json={"sku": f"{prefix}-CRM-CRP"})
    assert r3.status_code == 409


def test_inventory_update_and_reservation_floor(seller_b, b_product):
    vid = b_product["variants"][0]["id"]
    stock_before = int(_psql(f"SELECT stock_quantity FROM product_variants WHERE id='{vid}'"))
    try:
        r = seller_b.patch(f"{API}/seller/variants/{vid}/inventory", json={"stock_quantity": stock_before + 5})
        assert r.status_code == 200
        assert r.json()["stock_quantity"] == stock_before + 5
        # active reservation floor: guest reserves 1, then seller cannot drop stock to 0
        g = requests.Session()
        assert g.post(f"{API}/cart/items", json={
            "product_id": b_product["id"], "variant_id": vid, "quantity": 1,
        }).status_code == 201
        order = g.post(f"{API}/checkout/orders", json={
            "idempotency_key": uuid.uuid4().hex, "shipping_method": "standard",
            "locale": "en", "email": "floor@example.com", "address": ADDR,
        })
        assert order.status_code == 201
        r2 = seller_b.patch(f"{API}/seller/variants/{vid}/inventory", json={"stock_quantity": 0})
        assert r2.status_code == 409, r2.text
        assert r2.json()["detail"]["error"] == "below_active_reservations"
        assert r2.json()["detail"]["active_reservations"] == 1
        # seller cannot touch reservations table via API (no endpoint); cancel to release
        g.post(f"{API}/payments/mock/pay", json={
            "merchant_trans_id": order.json()["payment"]["merchant_trans_id"],
            "order_number": order.json()["order_number"], "scenario": "CANCELLED",
            "access_token": order.json()["access_token"],
        })
        g.delete(f"{API}/cart")
    finally:
        seller_b.patch(f"{API}/seller/variants/{vid}/inventory", json={"stock_quantity": stock_before})


# ---------------- seller orders + multi-seller partition ----------------

def test_multiseller_order_partition(seller_a, seller_b, a_product, b_product):
    _, order = _paid_multiseller_order(a_product, b_product)
    on = order["order_number"]
    a_view = seller_a.get(f"{API}/seller/orders/{on}")
    b_view = seller_b.get(f"{API}/seller/orders/{on}")
    assert a_view.status_code == 200 and b_view.status_code == 200
    aj, bj = a_view.json(), b_view.json()
    a_skus = {i["sku"] for i in aj["items"]}
    b_skus = {i["sku"] for i in bj["items"]}
    assert a_skus == {"GSOZH-BGE-M"} and b_skus == {b_product["variants"][0]["sku"]}
    assert not (a_skus & b_skus), "multi-seller order partitioned"
    assert aj["seller_subtotal"] == 499000, "A subtotal = own lines only"
    assert bj["seller_subtotal"] == b_product["variants"][0]["price_override"] or bj["seller_subtotal"] > 0
    # no cross-seller financial leakage
    assert "grand_total" not in aj and "subtotal" not in aj, "order-level totals withheld from seller"
    assert "email" not in aj.get("customer", {}), "customer email not exposed"
    # immutable snapshots present
    item = aj["items"][0]
    for f in ("product_name", "sku", "option_values", "unit_price", "quantity", "line_total", "seller_id"):
        assert item.get(f) not in (None, "")
    # list view scoped too
    a_list = seller_a.get(f"{API}/seller/orders").json()["items"]
    assert any(o["order_number"] == on for o in a_list)
    a_row = next(o for o in a_list if o["order_number"] == on)
    assert a_row["item_count"] == 1 and a_row["seller_subtotal"] == 499000


def test_seller_cannot_read_order_without_own_items(seller_a, b_product):
    # pure-B order
    s = _login(*CUSTOMER)
    s.delete(f"{API}/cart")
    b_var = b_product["variants"][0]
    s.post(f"{API}/cart/items", json={"product_id": b_product["id"], "variant_id": b_var["id"], "quantity": 1})
    order = s.post(f"{API}/checkout/orders", json={
        "idempotency_key": uuid.uuid4().hex, "shipping_method": "standard",
        "locale": "en", "address": ADDR,
    }).json()
    assert seller_a.get(f"{API}/seller/orders/{order['order_number']}").status_code == 404
    # cleanup
    s.post(f"{API}/payments/mock/pay", json={
        "merchant_trans_id": order["payment"]["merchant_trans_id"],
        "order_number": order["order_number"], "scenario": "CANCELLED",
    })
    s.delete(f"{API}/cart")


def test_fulfillment_lifecycle_and_isolation(seller_a, seller_b, a_product, b_product):
    _, order = _paid_multiseller_order(a_product, b_product)
    on = order["order_number"]
    # invalid jump
    r = seller_a.patch(f"{API}/seller/orders/{on}/fulfillment", json={"status": "delivered"})
    assert r.status_code == 400 and r.json()["detail"]["error"] == "invalid_transition"
    # forward path with tracking
    r = seller_a.patch(f"{API}/seller/orders/{on}/fulfillment", json={"status": "processing"})
    assert r.status_code == 200 and r.json()["fulfillment_status"] == "processing"
    assert r.json()["order_status"] == "processing", "global derives from seller fulfillments"
    r = seller_a.patch(f"{API}/seller/orders/{on}/fulfillment", json={
        "status": "shipped", "tracking_number": "UZ-TRK-7788", "shipping_carrier": "BTS Cargo",
    })
    assert r.json()["fulfillment_status"] == "shipped"
    assert r.json()["tracking_number"] == "UZ-TRK-7788"
    # A delivers own portion — B still pending → global must NOT be delivered
    r = seller_a.patch(f"{API}/seller/orders/{on}/fulfillment", json={"status": "delivered"})
    assert r.json()["fulfillment_status"] == "delivered"
    assert r.json()["order_status"] != "delivered", "one seller cannot complete a multi-seller order"
    # B's row untouched by A's actions
    b_view = seller_b.get(f"{API}/seller/orders/{on}").json()
    assert b_view["fulfillment"]["status"] == "pending"
    # backward transition rejected
    r = seller_a.patch(f"{API}/seller/orders/{on}/fulfillment", json={"status": "processing"})
    assert r.status_code == 400 and r.json()["detail"]["error"] == "invalid_transition"
    # B completes own portion → global delivered
    seller_b.patch(f"{API}/seller/orders/{on}/fulfillment", json={"status": "processing"})
    seller_b.patch(f"{API}/seller/orders/{on}/fulfillment", json={"status": "shipped"})
    rb = seller_b.patch(f"{API}/seller/orders/{on}/fulfillment", json={"status": "delivered"})
    assert rb.json()["order_status"] == "delivered", "all sellers delivered → global delivered"


def test_fulfillment_tracking_validation(seller_a, a_product, b_product):
    _, order = _paid_multiseller_order(a_product, b_product)
    on = order["order_number"]
    r = seller_a.patch(f"{API}/seller/orders/{on}/fulfillment", json={
        "status": "processing", "tracking_number": "<script>alert(1)</script>",
    })
    assert r.status_code == 400 and r.json()["detail"]["error"] == "invalid_tracking"
    # cleanup forward to delivered not needed; leave pending


def test_unpaid_order_cannot_be_fulfilled(seller_b, b_product):
    s = _login(*CUSTOMER)
    s.delete(f"{API}/cart")
    b_var = b_product["variants"][0]
    s.post(f"{API}/cart/items", json={"product_id": b_product["id"], "variant_id": b_var["id"], "quantity": 1})
    order = s.post(f"{API}/checkout/orders", json={
        "idempotency_key": uuid.uuid4().hex, "shipping_method": "standard",
        "locale": "en", "address": ADDR,
    }).json()
    r = seller_b.patch(f"{API}/seller/orders/{order['order_number']}/fulfillment", json={"status": "processing"})
    assert r.status_code == 409 and r.json()["detail"]["error"] == "payment_not_eligible"
    assert r.json()["detail"]["payment_state"] == "unpaid"
    # cleanup
    s.post(f"{API}/payments/mock/pay", json={
        "merchant_trans_id": order["payment"]["merchant_trans_id"],
        "order_number": order["order_number"], "scenario": "CANCELLED",
    })
    s.delete(f"{API}/cart")
