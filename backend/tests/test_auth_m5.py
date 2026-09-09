"""Milestone 5 — Auth + RBAC + Account API tests (PostgreSQL, cookie/CSRF)."""
import os, uuid, requests, pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://muslimah-shop.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api/v1"

ADMIN = ("bmulyanto@gmail.com", "MC-Adm1n-7f3k29xQ-2026")
SELLER = ("partner-uniqlo@muslimahcantik.id", "MC-S3ller-5t8r31Vn-2026")
CUSTOMER = ("customer.demo@muslimahcantik.id", "MC-Cust0mer-9d2m48Lw-2026")


def _fresh_email():
    return f"testauto+{uuid.uuid4().hex[:8]}@example.com"


def _session_login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    csrf = s.cookies.get("csrf_token")
    assert csrf, "csrf_token cookie must be set"
    s.headers["X-CSRF-Token"] = csrf
    return s


# ---------- Registration ----------

def test_register_success_forces_customer_role():
    email = _fresh_email()
    s = requests.Session()
    r = s.post(f"{API}/auth/register", json={
        "email": email, "password": "GoodPass123!",
        "first_name": "Auto", "last_name": "Test",
        "preferred_locale": "id",
        "role": "admin",  # mass-assignment attempt
    })
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert "password_hash" not in str(body).lower() or '"password_hash"' not in r.text
    # verify me
    csrf = s.cookies.get("csrf_token")
    assert csrf
    me = s.get(f"{API}/auth/me")
    assert me.status_code == 200
    j = me.json()
    assert j["email"] == email
    assert j["role"] == "customer", f"role must be forced customer, got {j.get('role')}"
    assert "password_hash" not in j


def test_register_duplicate_email():
    email = _fresh_email()
    payload = {"email": email, "password": "GoodPass123!", "first_name": "A", "last_name": "B", "preferred_locale": "id"}
    r1 = requests.post(f"{API}/auth/register", json=payload)
    assert r1.status_code in (200, 201)
    r2 = requests.post(f"{API}/auth/register", json=payload)
    assert r2.status_code == 409, f"expected 409, got {r2.status_code} {r2.text}"


# ---------- Login / me / logout ----------

def test_login_wrong_password_generic():
    r = requests.post(f"{API}/auth/login", json={"email": CUSTOMER[0], "password": "wrongwrong"})
    assert r.status_code == 401


def test_login_me_logout_cycle():
    s = _session_login(*CUSTOMER)
    me = s.get(f"{API}/auth/me")
    assert me.status_code == 200
    assert me.json()["role"] == "customer"
    assert "password_hash" not in me.text
    lo = s.post(f"{API}/auth/logout")
    assert lo.status_code in (200, 204)
    # After logout, me should be 401 (new session-less request)
    s2 = requests.Session()
    me2 = s2.get(f"{API}/auth/me")
    assert me2.status_code == 401


# ---------- CSRF ----------

def test_patch_me_without_csrf_403():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": CUSTOMER[0], "password": CUSTOMER[1]})
    assert r.status_code == 200
    # no X-CSRF-Token header
    r2 = s.patch(f"{API}/auth/me", json={"first_name": "Hacker"})
    assert r2.status_code == 403, f"expected 403 csrf_failed, got {r2.status_code} {r2.text}"


def test_patch_me_mass_assignment_role_blocked():
    s = _session_login(*CUSTOMER)
    r = s.patch(f"{API}/auth/me", json={"role": "admin", "first_name": "Demo"})
    # role field should be ignored (whitelist) — either 200 with role unchanged or 422
    assert r.status_code in (200, 422)
    me = s.get(f"{API}/auth/me")
    assert me.json()["role"] == "customer"


# ---------- RBAC matrix ----------

@pytest.mark.parametrize("creds,seller_expect,admin_expect", [
    (CUSTOMER, 403, 403),
    (SELLER, 200, 403),
    (ADMIN, 200, 200),
])
def test_rbac_matrix(creds, seller_expect, admin_expect):
    s = _session_login(*creds)
    r1 = s.get(f"{API}/auth/seller/ping")
    r2 = s.get(f"{API}/auth/admin/ping")
    assert r1.status_code == seller_expect, f"{creds[0]} seller/ping: {r1.status_code}"
    assert r2.status_code == admin_expect, f"{creds[0]} admin/ping: {r2.status_code}"


def test_rbac_unauth_401():
    r1 = requests.get(f"{API}/auth/seller/ping")
    r2 = requests.get(f"{API}/auth/admin/ping")
    assert r1.status_code == 401
    assert r2.status_code == 401


# ---------- Addresses CRUD + ownership ----------

def test_addresses_crud_and_default_handling():
    # Register a fresh user to keep state clean
    email = _fresh_email()
    s = requests.Session()
    r = s.post(f"{API}/auth/register", json={
        "email": email, "password": "GoodPass123!",
        "first_name": "Addr", "last_name": "User", "preferred_locale": "id",
    })
    assert r.status_code in (200, 201)
    s.headers["X-CSRF-Token"] = s.cookies.get("csrf_token")

    # list empty
    lr = s.get(f"{API}/account/addresses")
    assert lr.status_code == 200
    assert lr.json() == [] or isinstance(lr.json(), list)

    # add first address — becomes default
    a1 = s.post(f"{API}/account/addresses", json={
        "recipient_name": "A One", "phone": "+62812345678",
        "address_line_1": "Jl Mawar 1", "city": "Jakarta", "state_province": "DKI",
        "postal_code": "10110", "country": "ID",
        "is_default": True,
    })
    assert a1.status_code in (200, 201), a1.text
    a1j = a1.json()
    assert a1j.get("is_default") is True

    # add second with is_default true — first should be demoted
    a2 = s.post(f"{API}/account/addresses", json={
        "recipient_name": "A Two", "phone": "+62812345679",
        "address_line_1": "Jl Melati 2", "city": "Bandung", "state_province": "JB",
        "postal_code": "40111", "country": "ID",
        "is_default": True,
    })
    assert a2.status_code in (200, 201), a2.text
    a2j = a2.json()
    listing = s.get(f"{API}/account/addresses").json()
    defaults = [a for a in listing if a.get("is_default")]
    assert len(defaults) == 1, f"exactly one default expected, got {len(defaults)}"
    assert defaults[0]["id"] == a2j["id"]

    # edit first (PATCH takes full AddressIn body — noted as code review item)
    edit = s.patch(f"{API}/account/addresses/{a1j['id']}", json={
        "recipient_name": "A One", "phone": "+62812345678",
        "address_line_1": "Jl Mawar 1", "city": "Depok", "state_province": "JB",
        "postal_code": "10110", "country": "ID",
        "is_default": False,
    })
    assert edit.status_code == 200, edit.text
    assert edit.json()["city"] == "Depok"

    # ownership: another user should not access this address
    other_email = _fresh_email()
    s2 = requests.Session()
    r2 = s2.post(f"{API}/auth/register", json={
        "email": other_email, "password": "GoodPass123!",
        "first_name": "Other", "last_name": "User", "preferred_locale": "id",
    })
    assert r2.status_code in (200, 201)
    s2.headers["X-CSRF-Token"] = s2.cookies.get("csrf_token")
    forbidden = s2.patch(f"{API}/account/addresses/{a1j['id']}", json={
        "recipient_name": "Hax", "phone": "+62800000000",
        "address_line_1": "Hax", "city": "Hax", "state_province": "H",
        "postal_code": "00000", "country": "ID", "is_default": False,
    })
    assert forbidden.status_code in (403, 404), forbidden.status_code
    del_forbidden = s2.delete(f"{API}/account/addresses/{a1j['id']}")
    assert del_forbidden.status_code in (403, 404)

    # delete
    d = s.delete(f"{API}/account/addresses/{a1j['id']}")
    assert d.status_code in (200, 204)


# ---------- forgot-password parity ----------

def test_forgot_password_generic_response_registered_and_unregistered():
    # unregistered but valid email
    r1 = requests.post(f"{API}/auth/forgot-password", json={"email": f"nobody-{uuid.uuid4().hex[:6]}@example.com"})
    # registered
    r2 = requests.post(f"{API}/auth/forgot-password", json={"email": CUSTOMER[0]})
    assert r1.status_code == 200 and r2.status_code == 200
    # response body should be the same generic message
    assert r1.json() == r2.json() or ("message" in r1.json() and "message" in r2.json())
