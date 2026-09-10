"""Milestone 6 — Cart + Wishlist API tests (PostgreSQL, guest + auth).

Fresh registrations are rate-limited (10/15min/IP), so most authenticated
tests reuse the seeded customer account and clean up cart/wishlist state.
Only true multi-user isolation tests register fresh accounts (2 total).
"""
import os, uuid, requests, pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
API = f"{BASE}/api/v1"

CUSTOMER = ("customer.demo@muslimahcantik.id", "MC-Cust0mer-9d2m48Lw-2026")

HOODIE_SLUG = "gray-sweat-oversized-full-zip-hoodie"
ABAYA_SLUG = "abaya-classic-black"


def _product(slug):
    r = requests.get(f"{API}/catalog/products/{slug}")
    assert r.status_code == 200, f"catalog fetch failed for {slug}: {r.status_code}"
    return r.json()


@pytest.fixture(scope="module")
def hoodie():
    p = _product(HOODIE_SLUG)
    v = {x["sku"]: x for x in p["variants"]}
    assert v["GSOZH-BLK-XXL"]["stock_quantity"] == 0, "seed: BLK-XXL must be OOS"
    assert v["GSOZH-GRY-XS"]["stock_quantity"] == 2, "seed: GRY-XS must have stock 2"
    assert v["GSOZH-NVY-XXL"]["price_override"] == 519000, "seed: NVY-XXL override 519000"
    return {
        "id": p["id"],
        "base_price": p["base_price"],
        "oos": v["GSOZH-BLK-XXL"],
        "low": v["GSOZH-GRY-XS"],
        "normal": v["GSOZH-BGE-M"],
        "override": v["GSOZH-NVY-XXL"],
    }


@pytest.fixture(scope="module")
def abaya():
    p = _product(ABAYA_SLUG)
    v = next(x for x in p["variants"] if x["sku"] == "ACBK-BLK-M")
    return {"id": p["id"], "base_price": p["base_price"], "variant": v}


def _register():
    s = requests.Session()
    email = f"testauto+{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{API}/auth/register", json={
        "email": email, "password": "GoodPass123!",
        "first_name": "M6", "last_name": "Test", "preferred_locale": "en",
    })
    assert r.status_code in (200, 201), f"register failed {r.status_code} {r.text}"
    csrf = s.cookies.get("csrf_token")
    assert csrf, "csrf_token cookie must be set after register"
    s.headers["X-CSRF-Token"] = csrf
    return s, email


def _login(email=CUSTOMER[0], password=CUSTOMER[1]):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    csrf = s.cookies.get("csrf_token")
    assert csrf
    s.headers["X-CSRF-Token"] = csrf
    return s


def _add(session, product_id, variant_id, quantity=1):
    return session.post(f"{API}/cart/items", json={
        "product_id": product_id, "variant_id": variant_id, "quantity": quantity,
    })


def _clear_cart(session):
    session.delete(f"{API}/cart")


def _unwish(session, product_id):
    session.delete(f"{API}/wishlist/items/{product_id}")


# ---------------- Guest cart ----------------

def test_guest_cart_empty_initially():
    s = requests.Session()
    r = s.get(f"{API}/cart")
    assert r.status_code == 200
    j = r.json()
    assert j["items"] == [] and j["subtotal"] == 0 and j["item_count"] == 0
    assert j["currency"] == "UZS"
    assert "guest_cart_token" not in s.cookies, "empty GET must not issue a guest token"


def test_guest_add_sets_httponly_token_and_prices(hoodie):
    s = requests.Session()
    r = _add(s, hoodie["id"], hoodie["normal"]["id"], 2)
    assert r.status_code == 201, r.text
    token = s.cookies.get("guest_cart_token")
    assert token and len(token) >= 32, "server must issue opaque guest token"
    sc = r.headers.get("Set-Cookie", "")
    assert "httponly" in sc.lower(), f"guest cookie must be HttpOnly: {sc}"
    j = r.json()
    assert j["item_count"] == 2
    item = j["items"][0]
    assert item["unit_price"] == hoodie["base_price"], "price must be server-authoritative"
    assert item["line_total"] == 2 * hoodie["base_price"]
    assert j["subtotal"] == 2 * hoodie["base_price"] and isinstance(j["subtotal"], int)
    assert item["sku"] == hoodie["normal"]["sku"]
    assert item["availability"] == "in_stock"
    assert {"en", "id", "uz", "ru"} <= set(item["translations"].keys())


def test_guest_token_not_client_controllable(hoodie):
    forged = "forged-guest-token-0123456789abcdef"
    r = requests.post(f"{API}/cart/items",
                      json={"product_id": hoodie["id"], "variant_id": hoodie["normal"]["id"], "quantity": 1},
                      cookies={"guest_cart_token": forged})
    assert r.status_code == 201, r.text
    new_token = r.cookies.get("guest_cart_token")
    assert new_token and new_token != forged, "forged guest token must be replaced by a server-issued one"
    assert r.json()["item_count"] == 1


def test_add_out_of_stock_rejected(hoodie):
    s = requests.Session()
    r = _add(s, hoodie["id"], hoodie["oos"]["id"], 1)
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "insufficient_stock"
    assert r.json()["detail"]["available"] == 0
    assert s.get(f"{API}/cart").json()["item_count"] == 0


def test_add_variant_from_other_product_rejected(hoodie, abaya):
    s = requests.Session()
    r = _add(s, hoodie["id"], abaya["variant"]["id"], 1)
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_variant"


def test_add_unknown_product_404(hoodie):
    s = requests.Session()
    r = _add(s, "z" * 32, hoodie["normal"]["id"], 1)
    assert r.status_code == 404


def test_add_merges_same_variant_and_caps_stock(hoodie):
    s = requests.Session()
    low = hoodie["low"]  # stock 2
    r1 = _add(s, hoodie["id"], low["id"], 1)
    assert r1.status_code == 201
    r2 = _add(s, hoodie["id"], low["id"], 1)
    assert r2.status_code == 201
    j = r2.json()
    assert len(j["items"]) == 1, "same variant must merge into one line"
    assert j["items"][0]["quantity"] == 2
    r3 = _add(s, hoodie["id"], low["id"], 1)
    assert r3.status_code == 400
    d = r3.json()["detail"]
    assert d["error"] == "insufficient_stock" and d["available"] == 2 and d["in_cart"] == 2
    assert s.get(f"{API}/cart").json()["items"][0]["quantity"] == 2, "rejected add must not mutate cart"


def test_update_quantity_enforces_stock(hoodie):
    s = requests.Session()
    low = hoodie["low"]
    item = _add(s, hoodie["id"], low["id"], 1).json()["items"][0]
    r_bad = s.patch(f"{API}/cart/items/{item['id']}", json={"quantity": 3})
    assert r_bad.status_code == 400
    assert r_bad.json()["detail"]["error"] == "insufficient_stock"
    r_ok = s.patch(f"{API}/cart/items/{item['id']}", json={"quantity": 2})
    assert r_ok.status_code == 200
    assert r_ok.json()["items"][0]["quantity"] == 2
    r_zero = s.patch(f"{API}/cart/items/{item['id']}", json={"quantity": 0})
    assert r_zero.status_code == 422, "quantity must be >= 1"


def test_override_price_used(hoodie):
    s = requests.Session()
    r = _add(s, hoodie["id"], hoodie["override"]["id"], 1)
    assert r.status_code == 201
    item = r.json()["items"][0]
    assert item["unit_price"] == 519000, "price_override must win over base_price"
    assert item["compare_at_price"] in (None, 499000)


def test_remove_and_clear_cart(hoodie, abaya):
    s = requests.Session()
    _add(s, hoodie["id"], hoodie["normal"]["id"], 1)
    _add(s, abaya["id"], abaya["variant"]["id"], 1)
    j = s.get(f"{API}/cart").json()
    assert j["item_count"] == 2
    item_id = j["items"][0]["id"]
    r = s.delete(f"{API}/cart/items/{item_id}")
    assert r.status_code == 204
    assert s.get(f"{API}/cart").json()["item_count"] == 1
    r = s.delete(f"{API}/cart")
    assert r.status_code == 204
    assert s.get(f"{API}/cart").json()["item_count"] == 0


def test_guest_cart_isolation(hoodie):
    g1, g2 = requests.Session(), requests.Session()
    item = _add(g1, hoodie["id"], hoodie["normal"]["id"], 1).json()["items"][0]
    assert g2.patch(f"{API}/cart/items/{item['id']}", json={"quantity": 2}).status_code == 404
    assert g2.delete(f"{API}/cart/items/{item['id']}").status_code == 404
    assert g2.get(f"{API}/cart").json()["item_count"] == 0
    assert g1.get(f"{API}/cart").json()["item_count"] == 1


# ---------------- Authenticated cart ----------------

def test_auth_cart_and_csrf_enforcement(hoodie):
    s = _login()
    _clear_cart(s)
    r = s.get(f"{API}/cart")
    assert r.status_code == 200 and r.json()["item_count"] == 0
    # mutation without CSRF header must fail
    s_no_csrf = requests.Session()
    s_no_csrf.cookies.update(s.cookies)
    r = s_no_csrf.post(f"{API}/cart/items", json={
        "product_id": hoodie["id"], "variant_id": hoodie["normal"]["id"], "quantity": 1})
    assert r.status_code == 403, f"expected CSRF 403, got {r.status_code} {r.text}"
    # with CSRF header succeeds
    r = _add(s, hoodie["id"], hoodie["normal"]["id"], 1)
    assert r.status_code == 201, r.text
    assert r.json()["item_count"] == 1
    assert "guest_cart_token" not in s.cookies, "auth user must not receive a guest token"
    _clear_cart(s)


def test_auth_cart_isolation(hoodie):
    sa = _login()
    _clear_cart(sa)
    item = _add(sa, hoodie["id"], hoodie["normal"]["id"], 1).json()["items"][0]
    sb, _ = _register()
    assert sb.patch(f"{API}/cart/items/{item['id']}", json={"quantity": 2}).status_code == 404
    assert sb.delete(f"{API}/cart/items/{item['id']}").status_code == 404
    assert sb.get(f"{API}/cart").json()["item_count"] == 0
    _clear_cart(sa)


# ---------------- Guest -> auth merge ----------------

def test_merge_clamps_to_stock_and_reports_adjustments(hoodie):
    low = hoodie["low"]  # stock 2
    su = _login()
    _clear_cart(su)
    assert _add(su, hoodie["id"], low["id"], 1).status_code == 201
    g = requests.Session()
    assert _add(g, hoodie["id"], low["id"], 2).status_code == 201
    su.cookies.set("guest_cart_token", g.cookies.get("guest_cart_token"))
    r = su.post(f"{API}/cart/merge")
    assert r.status_code == 200, r.text
    j = r.json()
    adj = [a for a in j["adjustments"] if a["variant_id"] == low["id"]]
    assert adj and adj[0]["requested"] == 3 and adj[0]["applied"] == 2, f"adjustments: {j['adjustments']}"
    item = next(i for i in j["items"] if i["variant_id"] == low["id"])
    assert item["quantity"] == 2, "merged quantity must be clamped to stock"
    _clear_cart(su)


def test_merge_no_conflict_deletes_guest_cart(hoodie, abaya):
    su = _login()
    _clear_cart(su)
    assert _add(su, abaya["id"], abaya["variant"]["id"], 1).status_code == 201
    g = requests.Session()
    assert _add(g, hoodie["id"], hoodie["normal"]["id"], 3).status_code == 201
    token = g.cookies.get("guest_cart_token")
    su.cookies.set("guest_cart_token", token)
    r = su.post(f"{API}/cart/merge")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["adjustments"] == []
    skus = {i["sku"] for i in j["items"]}
    assert skus == {hoodie["normal"]["sku"], abaya["variant"]["sku"]}
    assert j["item_count"] == 4
    # guest cart must be gone server-side
    r2 = requests.get(f"{API}/cart", cookies={"guest_cart_token": token})
    assert r2.json()["item_count"] == 0, "guest cart must be deleted after merge"
    # repeat merge is a no-op
    r3 = su.post(f"{API}/cart/merge")
    assert r3.status_code == 200 and r3.json()["adjustments"] == []
    _clear_cart(su)


def test_merge_without_guest_cart(hoodie):
    su = _login()
    _clear_cart(su)
    assert _add(su, hoodie["id"], hoodie["normal"]["id"], 1).status_code == 201
    r = su.post(f"{API}/cart/merge")
    assert r.status_code == 200
    j = r.json()
    assert j["adjustments"] == [] and j["item_count"] == 1
    r_guest = requests.post(f"{API}/cart/merge")
    assert r_guest.status_code == 401, "merge must require auth"
    _clear_cart(su)


# ---------------- Wishlist ----------------

def test_wishlist_requires_auth(hoodie):
    s = requests.Session()
    assert s.get(f"{API}/wishlist").status_code == 401
    assert s.post(f"{API}/wishlist/items", json={"product_id": hoodie["id"]}).status_code == 401
    assert s.delete(f"{API}/wishlist/items/{hoodie['id']}").status_code == 401


def test_wishlist_add_idempotent_remove(hoodie):
    s = _login()
    _unwish(s, hoodie["id"])
    r = s.post(f"{API}/wishlist/items", json={"product_id": hoodie["id"]})
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["count"] == 1
    item = j["items"][0]
    assert item["slug"] == HOODIE_SLUG
    assert item["base_price"] == 499000 and isinstance(item["base_price"], int)
    assert item["stock_state"] in ("in_stock", "low_stock", "out_of_stock")
    assert {"en", "id", "uz", "ru"} <= set(item["translations"].keys())
    # idempotent re-add
    r2 = s.post(f"{API}/wishlist/items", json={"product_id": hoodie["id"]})
    assert r2.status_code == 201 and r2.json()["count"] == 1
    # remove
    r3 = s.delete(f"{API}/wishlist/items/{hoodie['id']}")
    assert r3.status_code == 200 and r3.json()["count"] == 0
    # removing again is a no-op
    r4 = s.delete(f"{API}/wishlist/items/{hoodie['id']}")
    assert r4.status_code == 200 and r4.json()["count"] == 0


def test_wishlist_unknown_product_404():
    s = _login()
    r = s.post(f"{API}/wishlist/items", json={"product_id": "z" * 32})
    assert r.status_code == 404


def test_wishlist_isolation(hoodie):
    sa = _login()
    _unwish(sa, hoodie["id"])
    sa.post(f"{API}/wishlist/items", json={"product_id": hoodie["id"]})
    sb, _ = _register()
    assert sb.get(f"{API}/wishlist").json()["count"] == 0
    assert sa.get(f"{API}/wishlist").json()["count"] == 1
    _unwish(sa, hoodie["id"])
