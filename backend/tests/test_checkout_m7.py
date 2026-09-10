"""Milestone 7 — Checkout + Orders + CLICK mock integration tests.

Covers: server-authoritative totals, idempotent order creation, immutable
snapshots, inventory reservations (reserve/commit/release/expire/TTL),
mock CLICK Prepare->Complete flows, duplicate safety, cart clearing rules,
guest order privacy, order history/detail ownership.
"""
import os, subprocess, threading, uuid, requests, pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://muslimah-shop.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api/v1"
DB_URL = "postgresql://muslimah:muslimah_dev_pass@localhost:5432/muslimah_cantik"

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


def _stock(variant_id):
    return int(_psql(f"SELECT stock_quantity FROM product_variants WHERE id='{variant_id}'"))


def _reservations(order_number):
    return _psql(
        "SELECT r.status || ':' || r.quantity FROM inventory_reservations r "
        f"JOIN orders o ON o.id = r.order_id WHERE o.order_number='{order_number}' ORDER BY r.id"
    )


def _product(slug):
    r = requests.get(f"{API}/catalog/products/{slug}")
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def serum():
    p = _product("brightening-serum-30ml")
    return {"id": p["id"], "base_price": p["base_price"], "variant": p["variants"][0]}


@pytest.fixture(scope="module")
def hoodie():
    p = _product("gray-sweat-oversized-full-zip-hoodie")
    v = {x["sku"]: x for x in p["variants"]}
    assert v["GSOZH-GRY-XS"]["stock_quantity"] == 2
    return {"id": p["id"], "base_price": p["base_price"], "low": v["GSOZH-GRY-XS"], "normal": v["GSOZH-BGE-M"]}


def _login(email=CUSTOMER[0], password=CUSTOMER[1]):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    s.headers["X-CSRF-Token"] = s.cookies.get("csrf_token")
    return s


def _register():
    s = requests.Session()
    email = f"testauto+{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{API}/auth/register", json={
        "email": email, "password": "GoodPass123!",
        "first_name": "M7", "last_name": "Test", "preferred_locale": "en",
    })
    assert r.status_code in (200, 201), r.text
    s.headers["X-CSRF-Token"] = s.cookies.get("csrf_token")
    return s, email


def _guest_with_cart(product_id, variant_id, qty=1):
    s = requests.Session()
    r = s.post(f"{API}/cart/items", json={"product_id": product_id, "variant_id": variant_id, "quantity": qty})
    assert r.status_code == 201, r.text
    return s


def _place_order(session, key=None, method="standard", email="guest@example.com", address=ADDR, **extra):
    payload = {
        "idempotency_key": key or uuid.uuid4().hex,
        "shipping_method": method, "locale": "en",
        "email": email, "address": address, **extra,
    }
    return session.post(f"{API}/checkout/orders", json=payload)


def _mock_pay(session, order_resp, scenario):
    return session.post(f"{API}/payments/mock/pay", json={
        "merchant_trans_id": order_resp["payment"]["merchant_trans_id"],
        "order_number": order_resp["order_number"],
        "scenario": scenario,
        "access_token": order_resp.get("access_token"),
    })


def _simulate(merchant_trans_id, scenario):
    return requests.post(f"{API}/payments/mock/simulate", json={
        "merchant_trans_id": merchant_trans_id, "scenario": scenario,
    })


# ---------------- options & quote (server-authoritative totals) ----------------

def test_checkout_options_guest(serum):
    s = _guest_with_cart(serum["id"], serum["variant"]["id"], 1)
    r = s.get(f"{API}/checkout/options")
    assert r.status_code == 200
    j = r.json()
    assert j["currency"] == "UZS"
    methods = {m["code"]: m["amount"] for m in j["shipping_methods"]}
    assert methods == {"standard": 30000, "express": 65000}
    assert j["payment_methods"] == [{"code": "click", "label": "CLICK"}]
    assert j["payment_mode"] == "mock"
    assert j["cart_subtotal"] == serum["base_price"]
    s.delete(f"{API}/cart")


def test_quote_server_authoritative(serum):
    s = _guest_with_cart(serum["id"], serum["variant"]["id"], 1)
    r = s.post(f"{API}/checkout/quote", json={"shipping_method": "standard"})
    assert r.status_code == 200
    j = r.json()
    assert j["subtotal"] == 149000 and j["shipping_amount"] == 30000
    assert j["grand_total"] == 179000 and isinstance(j["grand_total"], int)
    r2 = s.post(f"{API}/checkout/quote", json={"shipping_method": "express"})
    assert r2.json()["grand_total"] == 149000 + 65000
    s.delete(f"{API}/cart")


def test_quote_free_standard_over_threshold(serum):
    s = _guest_with_cart(serum["id"], serum["variant"]["id"], 4)  # 596,000 >= 550,000
    j = s.post(f"{API}/checkout/quote", json={"shipping_method": "standard"}).json()
    assert j["shipping_amount"] == 0 and j["grand_total"] == j["subtotal"]
    j2 = s.post(f"{API}/checkout/quote", json={"shipping_method": "express"}).json()
    assert j2["shipping_amount"] == 65000, "express is never free"
    s.delete(f"{API}/cart")


def test_quote_unknown_method_and_empty_cart(serum):
    s = _guest_with_cart(serum["id"], serum["variant"]["id"], 1)
    assert s.post(f"{API}/checkout/quote", json={"shipping_method": "teleport"}).status_code == 400
    s.delete(f"{API}/cart")
    assert s.post(f"{API}/checkout/quote", json={"shipping_method": "standard"}).status_code == 400


# ---------------- order creation ----------------

def test_guest_checkout_validation(serum):
    s = _guest_with_cart(serum["id"], serum["variant"]["id"], 1)
    r = _place_order(s, email=None)
    assert r.status_code == 400 and r.json()["detail"] == "email_required"
    r2 = s.post(f"{API}/checkout/orders", json={
        "idempotency_key": uuid.uuid4().hex, "shipping_method": "standard",
        "email": "g@example.com",
    })
    assert r2.status_code == 400 and r2.json()["detail"] == "address_required"
    s.delete(f"{API}/cart")


def test_guest_checkout_creates_order_reservation_payment(serum):
    s = _guest_with_cart(serum["id"], serum["variant"]["id"], 2)
    stock_before = _stock(serum["variant"]["id"])
    r = _place_order(s, method="express")
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["order_number"].startswith("MC-")
    assert j["access_token"], "guest must receive opaque access token"
    assert j["grand_total"] == 2 * 149000 + 65000
    assert j["payment"]["amount"] == j["grand_total"], "payment amount == order grand_total"
    assert j["payment"]["merchant_trans_id"] and j["payment"]["merchant_trans_id"] != "guest@example.com"
    assert j["mock_payment_url"].startswith("/checkout/payment/mock")
    res = _reservations(j["order_number"])
    assert res == "active:2", f"reservation must be active:2, got {res}"
    assert _stock(serum["variant"]["id"]) == stock_before, "stock NOT reduced at reservation time"
    # cart intentionally retained until payment succeeds
    assert s.get(f"{API}/cart").json()["item_count"] == 2
    # cleanup: cancel payment -> releases reservation
    assert _mock_pay(s, j, "CANCELLED").status_code == 200


def test_order_creation_idempotent(serum):
    s = _guest_with_cart(serum["id"], serum["variant"]["id"], 1)
    key = uuid.uuid4().hex
    r1 = _place_order(s, key=key)
    r2 = _place_order(s, key=key)
    assert r1.status_code == 201 and r2.status_code in (200, 201)
    j1, j2 = r1.json(), r2.json()
    assert j1["order_number"] == j2["order_number"], "retry must return the SAME order"
    assert _reservations(j1["order_number"]) == "active:1", "no duplicate reservations"
    count = _psql(f"SELECT count(*) FROM orders WHERE idempotency_key='{key}'")
    assert count == "1", "exactly one order row"
    _mock_pay(s, j1, "CANCELLED")


def test_checkout_blocks_oversell_via_reservation(hoodie):
    low = hoodie["low"]  # stock 2
    ga = _guest_with_cart(hoodie["id"], low["id"], 2)
    ra = _place_order(ga)
    assert ra.status_code == 201
    # cart itself does NOT reserve: guest B can still add to cart
    gb = _guest_with_cart(hoodie["id"], low["id"], 2)
    # ...but checkout must reject: 2 physical - 2 reserved = 0 available
    rb = _place_order(gb)
    assert rb.status_code == 409, rb.text
    assert rb.json()["detail"]["error"] == "insufficient_stock"
    assert rb.json()["detail"]["available"] == 0
    _mock_pay(ga, ra.json(), "CANCELLED")  # releases reservation
    # now B can check out
    rb2 = _place_order(gb)
    assert rb2.status_code == 201
    _mock_pay(gb, rb2.json(), "CANCELLED")


def test_concurrent_last_unit_protected(hoodie):
    low = hoodie["low"]  # stock 2
    sa = _guest_with_cart(hoodie["id"], low["id"], 2)
    sb = _guest_with_cart(hoodie["id"], low["id"], 2)
    results = {}

    def attempt(name, sess):
        r = _place_order(sess)
        results[name] = (r.status_code, sess, r.json() if r.status_code == 201 else None)

    t1 = threading.Thread(target=attempt, args=("a", sa))
    t2 = threading.Thread(target=attempt, args=("b", sb))
    t1.start(); t2.start(); t1.join(); t2.join()
    codes = sorted(v[0] for v in results.values())
    assert codes == [201, 409], f"exactly one checkout may win the last units, got {codes}"
    winner = next(v for v in results.values() if v[0] == 201)
    _mock_pay(winner[1], winner[2], "CANCELLED")


# ---------------- payment flows: commit / release / expire ----------------

def test_success_commits_stock_once_and_clears_cart(serum):
    s = _guest_with_cart(serum["id"], serum["variant"]["id"], 1)
    stock_before = _stock(serum["variant"]["id"])
    order = _place_order(s).json()
    mtid = order["payment"]["merchant_trans_id"]
    r = _mock_pay(s, order, "SUCCESS")
    assert r.status_code == 200, r.text
    j = r.json()
    assert [st["step"] for st in j["steps"]] == ["prepare", "complete"], "real Prepare->Complete path"
    assert all(st["error"] == 0 for st in j["steps"])
    assert j["payment_status"] == "paid" and j["order_status"] == "paid" and j["order_payment_state"] == "paid"
    assert _stock(serum["variant"]["id"]) == stock_before - 1, "stock decremented once"
    assert _reservations(order["order_number"]) == "committed:1"
    assert s.get(f"{API}/cart").json()["item_count"] == 0, "source cart cleared"
    # duplicate Complete via simulator must NOT decrement again
    r2 = _simulate(mtid, "DUPLICATE_COMPLETE")
    assert r2.status_code == 200
    assert _stock(serum["variant"]["id"]) == stock_before - 1, "duplicate Complete must not decrement twice"
    # unrelated guest cart untouched
    other = _guest_with_cart(serum["id"], serum["variant"]["id"], 1)
    assert other.get(f"{API}/cart").json()["item_count"] == 1
    other.delete(f"{API}/cart")


def test_failed_payment_releases_reservation_keeps_cart(serum):
    s = _guest_with_cart(serum["id"], serum["variant"]["id"], 1)
    stock_before = _stock(serum["variant"]["id"])
    order = _place_order(s).json()
    j = _mock_pay(s, order, "FAILED").json()
    assert j["payment_status"] == "failed"
    assert j["order_status"] == "cancelled", "failed payment cancels the one-shot order"
    assert _reservations(order["order_number"]) == "released:1"
    assert _stock(serum["variant"]["id"]) == stock_before, "no stock change on failure"
    assert s.get(f"{API}/cart").json()["item_count"] == 1, "cart retained after failure"
    s.delete(f"{API}/cart")


def test_cancelled_payment_releases_reservation(serum):
    s = _guest_with_cart(serum["id"], serum["variant"]["id"], 1)
    order = _place_order(s).json()
    j = _mock_pay(s, order, "CANCELLED").json()
    assert j["payment_status"] == "cancelled" and j["order_status"] == "cancelled"
    assert _reservations(order["order_number"]) == "released:1"
    assert s.get(f"{API}/cart").json()["item_count"] == 1
    s.delete(f"{API}/cart")


def test_timeout_does_not_mark_paid(serum):
    s = _guest_with_cart(serum["id"], serum["variant"]["id"], 1)
    stock_before = _stock(serum["variant"]["id"])
    order = _place_order(s).json()
    j = _mock_pay(s, order, "TIMEOUT").json()
    assert j["payment_status"] == "prepared", "timeout = unknown/pending, never paid"
    assert j["order_status"] == "pending_payment" and j["order_payment_state"] == "unpaid"
    assert _reservations(order["order_number"]) == "active:1", "reservation held until TTL"
    assert _stock(serum["variant"]["id"]) == stock_before
    _mock_pay(s, order, "CANCELLED")  # cleanup — complete error path from prepared


def test_expired_payment_releases_reservation(serum):
    s = _guest_with_cart(serum["id"], serum["variant"]["id"], 1)
    order = _place_order(s).json()
    j = _mock_pay(s, order, "EXPIRED").json()
    assert j["payment_status"] == "expired" and j["order_status"] == "cancelled"
    assert _reservations(order["order_number"]) == "released:1"
    s.delete(f"{API}/cart")


def test_reservation_ttl_lazy_expiry(serum):
    s = _guest_with_cart(serum["id"], serum["variant"]["id"], 1)
    order = _place_order(s).json()
    row = _psql(
        "SELECT r.expires_at > r.created_at FROM inventory_reservations r "
        f"JOIN orders o ON o.id=r.order_id WHERE o.order_number='{order['order_number']}'"
    )
    assert row == "t", "reservation carries a TTL"
    # force expiry and trigger lazy sweep via another checkout quote
    _psql(
        "UPDATE inventory_reservations SET expires_at = now() - interval '1 minute' "
        f"WHERE order_id = (SELECT id FROM orders WHERE order_number='{order['order_number']}')"
    )
    s2 = _guest_with_cart(serum["id"], serum["variant"]["id"], 1)
    r = s2.post(f"{API}/checkout/quote", json={"shipping_method": "standard"})
    assert r.status_code == 200
    assert _reservations(order["order_number"]).startswith("expired"), "TTL-expired reservation swept"
    s.delete(f"{API}/cart")
    s2.delete(f"{API}/cart")


def test_wrong_amount_and_invalid_signature_mutate_nothing(serum):
    s = _guest_with_cart(serum["id"], serum["variant"]["id"], 1)
    stock_before = _stock(serum["variant"]["id"])
    order = _place_order(s).json()
    mtid = order["payment"]["merchant_trans_id"]
    j1 = _simulate(mtid, "WRONG_AMOUNT").json()
    assert j1["payment_status"] != "paid" and j1["order_payment_state"] == "unpaid"
    assert _reservations(order["order_number"]) == "active:1"
    assert _stock(serum["variant"]["id"]) == stock_before
    assert s.get(f"{API}/cart").json()["item_count"] == 1
    j2 = _simulate(mtid, "INVALID_SIGNATURE").json()
    assert any(st.get("error") == -1 for st in j2["steps"]), "bad signature must be rejected (-1)"
    assert j2["payment_status"] != "paid"
    assert _stock(serum["variant"]["id"]) == stock_before
    # duplicate Prepare is a safe replay
    j3 = _simulate(mtid, "DUPLICATE_PREPARE").json()
    assert all(st["error"] == 0 for st in j3["steps"])
    _mock_pay(s, order, "CANCELLED")
    s.delete(f"{API}/cart")


def test_payment_events_have_no_secrets(serum):
    s = _guest_with_cart(serum["id"], serum["variant"]["id"], 1)
    order = _place_order(s).json()
    mtid = order["payment"]["merchant_trans_id"]
    _mock_pay(s, order, "SUCCESS")
    r = requests.get(f"{API}/payments/mock/status/{mtid}")
    assert r.status_code == 200
    types = [e["event_type"] for e in r.json()["events"]]
    assert "CREATE" in types and "PREPARE" in types and "COMPLETE" in types
    secret = ""
    for line in open("/app/backend/.env"):
        if line.startswith("CLICK_MOCK_SECRET_KEY="):
            secret = line.split("=", 1)[1].strip().strip('"')
    assert not secret or secret not in r.text, "signing secret must never appear in events"


def test_mock_pay_authorization(serum):
    s = _guest_with_cart(serum["id"], serum["variant"]["id"], 1)
    order = _place_order(s).json()
    # no token
    r = requests.post(f"{API}/payments/mock/pay", json={
        "merchant_trans_id": order["payment"]["merchant_trans_id"],
        "order_number": order["order_number"], "scenario": "SUCCESS",
    })
    assert r.status_code == 403
    # wrong token
    r2 = requests.post(f"{API}/payments/mock/pay", json={
        "merchant_trans_id": order["payment"]["merchant_trans_id"],
        "order_number": order["order_number"], "scenario": "SUCCESS",
        "access_token": "wrong-token",
    })
    assert r2.status_code == 403
    # adversarial scenarios not available on the customer endpoint
    r3 = s.post(f"{API}/payments/mock/pay", json={
        "merchant_trans_id": order["payment"]["merchant_trans_id"],
        "order_number": order["order_number"], "scenario": "WRONG_AMOUNT",
        "access_token": order["access_token"],
    })
    assert r3.status_code == 422
    _mock_pay(s, order, "CANCELLED")
    s.delete(f"{API}/cart")


def test_mock_gate_logic_unit():
    from fastapi import HTTPException
    from payments import routes as payment_routes
    original = payment_routes.CLICK_MODE
    try:
        for mode in ("test", "production"):
            payment_routes.CLICK_MODE = mode
            with pytest.raises(HTTPException) as exc:
                payment_routes._require_mock_mode()
            assert exc.value.status_code == 404, f"mock simulator must 404 in {mode} mode"
    finally:
        payment_routes.CLICK_MODE = original


# ---------------- authenticated checkout / addresses / orders ----------------

def test_auth_checkout_saved_address_and_snapshot_immutable(serum):
    s = _login()
    # ensure an address exists
    addr = s.post(f"{API}/account/addresses", json={
        "label": "M7", "recipient_name": "Buyer One", "phone": "+998901234567",
        "address_line_1": "42 Amir Temur Ave", "city": "Tashkent",
        "state_province": "Tashkent", "postal_code": "100084",
        "country_code": "UZ", "is_default": True,
    })
    assert addr.status_code == 201, addr.text
    address_id = addr.json()["id"]
    s.delete(f"{API}/cart")
    assert s.post(f"{API}/cart/items", json={
        "product_id": serum["id"], "variant_id": serum["variant"]["id"], "quantity": 1,
    }).status_code == 201
    r = _place_order(s, email=None, address=None, saved_address_id=address_id, method="standard")
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["access_token"] is None, "auth orders never expose guest tokens"
    # snapshot captured
    detail = s.get(f"{API}/account/orders/{j['order_number']}")
    assert detail.status_code == 200
    snap = detail.json()["shipping_address"]
    assert snap["recipient_name"] == "Buyer One" and snap["address_line_1"] == "42 Amir Temur Ave"
    assert detail.json()["email"] == CUSTOMER[0]
    # edit the saved address -> historical order must NOT change
    patch = s.patch(f"{API}/account/addresses/{address_id}", json={
        "label": "M7", "recipient_name": "Buyer One", "phone": "+998901234567",
        "address_line_1": "999 CHANGED STREET", "city": "Samarkand",
        "state_province": "Samarkand", "postal_code": "140100",
        "country_code": "UZ", "is_default": True,
    })
    assert patch.status_code == 200
    snap2 = s.get(f"{API}/account/orders/{j['order_number']}").json()["shipping_address"]
    assert snap2["address_line_1"] == "42 Amir Temur Ave", "order snapshot immutable"
    # order appears in history
    history = s.get(f"{API}/account/orders").json()
    assert any(o["order_number"] == j["order_number"] for o in history)
    # cleanup: cancel + delete address + cart
    _mock_pay(s, j, "CANCELLED")
    s.delete(f"{API}/account/addresses/{address_id}")
    s.delete(f"{API}/cart")


def test_saved_address_ownership_enforced(serum):
    sa = _login()
    addr = sa.post(f"{API}/account/addresses", json={
        "label": "M7-own", "recipient_name": "Owner", "phone": "+998901112244",
        "address_line_1": "7 Owner St", "city": "Tashkent",
        "state_province": "Tashkent", "postal_code": "100000",
        "country_code": "UZ", "is_default": False,
    })
    address_id = addr.json()["id"]
    sb, _ = _register()
    sb.post(f"{API}/cart/items", json={
        "product_id": serum["id"], "variant_id": serum["variant"]["id"], "quantity": 1,
    })
    r = _place_order(sb, email=None, address=None, saved_address_id=address_id)
    assert r.status_code == 404, "user B must never use user A's address"
    sa.delete(f"{API}/account/addresses/{address_id}")
    sb.delete(f"{API}/cart")


def test_order_item_snapshots_complete(serum):
    s = _guest_with_cart(serum["id"], serum["variant"]["id"], 1)
    order = _place_order(s).json()
    d = requests.get(
        f"{API}/orders/track",
        params={"order_number": order["order_number"], "token": order["access_token"]},
    )
    assert d.status_code == 200
    item = d.json()["items"][0]
    for field in ("product_id", "variant_id", "seller_id", "sku", "product_name",
                  "option_values", "unit_price", "quantity", "line_total"):
        assert item.get(field) not in (None, ""), f"snapshot field {field} missing"
    assert item["sku"] == serum["variant"]["sku"]
    assert item["unit_price"] == 149000 and item["line_total"] == 149000
    assert item["seller_id"], "seller_id snapshot mandatory for Seller milestone"
    _mock_pay(s, order, "CANCELLED")
    s.delete(f"{API}/cart")


def test_catalog_price_change_does_not_mutate_order(serum):
    s = _guest_with_cart(serum["id"], serum["variant"]["id"], 1)
    order = _place_order(s).json()
    pid = serum["id"]
    try:
        _psql(f"UPDATE products SET base_price = base_price + 7000 WHERE id='{pid}'")
        d = requests.get(
            f"{API}/orders/track",
            params={"order_number": order["order_number"], "token": order["access_token"]},
        ).json()
        assert d["items"][0]["unit_price"] == 149000, "historical price frozen"
        assert d["grand_total"] == 149000 + 30000
    finally:
        _psql(f"UPDATE products SET base_price = base_price - 7000 WHERE id='{pid}'")
    _mock_pay(s, order, "CANCELLED")
    s.delete(f"{API}/cart")


def test_cross_user_order_access_denied(serum):
    sa = _login()
    sa.delete(f"{API}/cart")
    sa.post(f"{API}/cart/items", json={
        "product_id": serum["id"], "variant_id": serum["variant"]["id"], "quantity": 1,
    })
    order = _place_order(sa, email=None).json()
    sb, _ = _register()
    r = sb.get(f"{API}/account/orders/{order['order_number']}")
    assert r.status_code == 404, "user B must never read user A's order"
    assert not any(o["order_number"] == order["order_number"] for o in sb.get(f"{API}/account/orders").json())
    # guest track endpoint must not expose an auth-owned order even with order_number
    r2 = requests.get(f"{API}/orders/track", params={
        "order_number": order["order_number"], "token": "whatever-token",
    })
    assert r2.status_code == 404
    _mock_pay(sa, order, "CANCELLED")
    sa.delete(f"{API}/cart")


def test_guest_lookup_requires_opaque_token(serum):
    s = _guest_with_cart(serum["id"], serum["variant"]["id"], 1)
    order = _place_order(s).json()
    ok = requests.get(f"{API}/orders/track", params={
        "order_number": order["order_number"], "token": order["access_token"],
    })
    assert ok.status_code == 200
    bad = requests.get(f"{API}/orders/track", params={
        "order_number": order["order_number"], "token": "guess-me-not-123",
    })
    assert bad.status_code == 404
    missing = requests.get(f"{API}/orders/track", params={"order_number": order["order_number"]})
    assert missing.status_code == 422, "token parameter is mandatory"
    _mock_pay(s, order, "CANCELLED")
    s.delete(f"{API}/cart")
