"""Milestone 7.1 — Late CLICK Complete + expired/released reservation safety.

HARD RULE under test: expired/released reservations are never committed
directly. A late Complete must reconcile atomically:
- stock available  -> auditable reacquisition (replacement reservation)
- stock unavailable -> explicit reconciliation states, no oversell,
  no negative stock, existing CLICK error code (-7 UPDATE_FAILURE).
"""
import os, subprocess, uuid, requests, pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
API = f"{BASE}/api/v1"
DB_URL = "postgresql://muslimah:muslimah_dev_pass@localhost:5432/muslimah_cantik"

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


def _set_stock(variant_id, n):
    _psql(f"UPDATE product_variants SET stock_quantity={n} WHERE id='{variant_id}'")


def _res_rows(order_number):
    out = _psql(
        "SELECT r.status || ':' || r.quantity || ':' || COALESCE(r.reacquired_from, '-') "
        "FROM inventory_reservations r JOIN orders o ON o.id = r.order_id "
        f"WHERE o.order_number='{order_number}' ORDER BY r.created_at, r.id"
    )
    return [line for line in out.splitlines() if line]


def _backdate_expiry(order_number):
    _psql(
        "UPDATE inventory_reservations SET expires_at = now() - interval '1 minute' "
        "WHERE status='active' AND order_id = "
        f"(SELECT id FROM orders WHERE order_number='{order_number}')"
    )


def _product(slug):
    r = requests.get(f"{API}/catalog/products/{slug}")
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def abaya():
    p = _product("abaya-classic-black")
    v = next(x for x in p["variants"] if x["sku"] == "ACBK-BLK-M")
    return {"product_id": p["id"], "variant_id": v["id"], "price": p["base_price"]}


def _guest_with_cart(product_id, variant_id, qty=1):
    s = requests.Session()
    r = s.post(f"{API}/cart/items", json={"product_id": product_id, "variant_id": variant_id, "quantity": qty})
    assert r.status_code == 201, r.text
    return s


def _place_order(session, **extra):
    payload = {
        "idempotency_key": uuid.uuid4().hex, "shipping_method": "standard",
        "locale": "en", "email": "guest@example.com", "address": ADDR, **extra,
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


def _sweep_via_quote(session):
    """Trigger the real lazy expiry sweep through a live quote request."""
    r = session.post(f"{API}/checkout/quote", json={"shipping_method": "standard"})
    return r


# ---------------- mandatory race test ----------------

def test_race_expire_b_reserves_delayed_a_complete(abaya):
    """stock=1: A reserves -> A expires -> B reserves -> late Complete for A.
    A must NOT commit B's unit; stock never negative; explicit review state."""
    pid, vid = abaya["product_id"], abaya["variant_id"]
    original = _stock(vid)
    try:
        _set_stock(vid, 1)
        # A: checkout reserves the only unit, payment prepared (timeout = no complete)
        sa = _guest_with_cart(pid, vid, 1)
        order_a = _place_order(sa).json()
        prep = _mock_pay(sa, order_a, "TIMEOUT").json()
        assert prep["payment_status"] == "prepared"
        # while A holds the reservation, B cannot check out
        sb_probe = _guest_with_cart(pid, vid, 1)
        blocked = _place_order(sb_probe)
        assert blocked.status_code == 409, "active reservation must block B"
        # A's reservation TTL expires (backdated + real lazy sweep)
        _backdate_expiry(order_a["order_number"])
        sweep = _sweep_via_quote(sb_probe)
        assert sweep.status_code == 200, "after expiry the unit is quotable again"
        assert _res_rows(order_a["order_number"]) == ["expired:1:-"]
        # B reserves the freed unit
        order_b = _place_order(sb_probe)
        assert order_b.status_code == 201
        # delayed valid Complete arrives for A -> must NOT take B's unit
        late = _mock_pay(sa, order_a, "SUCCESS").json()
        complete_step = [s for s in late["steps"] if s["step"] == "complete"][0]
        assert complete_step["error"] == -7, "existing CLICK UPDATE_FAILURE code, no invented code"
        assert late["payment_status"] == "reconciliation_required"
        assert late["order_status"] == "payment_review"
        assert late["order_payment_state"] == "review"
        assert _stock(vid) == 1, "physical stock untouched — B's unit safe"
        assert _res_rows(order_a["order_number"]) == ["expired:1:-"], \
            "expired reservation untouched, no replacement created"
        assert sa.get(f"{API}/cart").json()["item_count"] == 1, "cart preserved, not destroyed"
        # repeated delayed Complete -> idempotent, still no effects
        late2 = _mock_pay(sa, order_a, "SUCCESS").json()
        assert late2["payment_status"] == "reconciliation_required"
        assert _stock(vid) == 1
        assert _res_rows(order_a["order_number"]) == ["expired:1:-"]
        # B pays normally -> exactly one unit committed, stock 0
        paid_b = _mock_pay(sb_probe, order_b.json(), "SUCCESS").json()
        assert paid_b["payment_status"] == "paid"
        assert _stock(vid) == 0
        # A retries again — stock exhausted (0 - 0 active = 0) -> still review
        late3 = _mock_pay(sa, order_a, "SUCCESS").json()
        assert late3["payment_status"] == "reconciliation_required"
        assert _stock(vid) == 0, "never negative"
        assert _res_rows(order_a["order_number"]) == ["expired:1:-"]
    finally:
        _psql(
            "UPDATE inventory_reservations SET status='released', released_at=now() "
            "WHERE status='active' AND product_variant_id = "
            f"'{vid}'"
        )
        _set_stock(vid, original)
        sa.delete(f"{API}/cart")
        sb_probe.delete(f"{API}/cart")


# ---------------- late complete with stock available ----------------

def test_late_complete_reacquires_safely(abaya):
    """stock=2: A reserves 1 -> expires -> nobody took it -> delayed Complete A.
    System reacquires atomically: final stock exactly 1, auditable replacement."""
    pid, vid = abaya["product_id"], abaya["variant_id"]
    original = _stock(vid)
    try:
        _set_stock(vid, 2)
        sa = _guest_with_cart(pid, vid, 1)
        order_a = _place_order(sa).json()
        _mock_pay(sa, order_a, "TIMEOUT")
        _backdate_expiry(order_a["order_number"])
        sb = _guest_with_cart(pid, vid, 1)
        sweep = _sweep_via_quote(sb)
        assert sweep.status_code == 200
        assert _res_rows(order_a["order_number"]) == ["expired:1:-"]
        assert _stock(vid) == 2, "expiry frees availability but not physical stock"

        late = _mock_pay(sa, order_a, "SUCCESS").json()
        assert late["payment_status"] == "paid" and late["order_status"] == "paid"
        assert _stock(vid) == 1, "exactly one unit reacquired"
        rows = _res_rows(order_a["order_number"])
        assert len(rows) == 2, f"original expired row + one replacement, got {rows}"
        assert rows[0] == "expired:1:-", "historical expired row untouched"
        original_id = _psql(
            "SELECT r.id FROM inventory_reservations r JOIN orders o ON o.id=r.order_id "
            f"WHERE o.order_number='{order_a['order_number']}' AND r.status='expired'"
        )
        assert rows[1] == f"committed:1:{original_id}", \
            "replacement reservation committed with auditable reacquired_from link"
        assert sa.get(f"{API}/cart").json()["item_count"] == 0, "source cart cleared once"

        # repeated delayed Complete -> zero further effects
        again = _mock_pay(sa, order_a, "SUCCESS").json()
        assert again["payment_status"] == "paid"
        assert _stock(vid) == 1, "no duplicate decrement"
        assert _res_rows(order_a["order_number"]) == rows, "no duplicate replacement"

        # remaining unit is still purchasable by B
        order_b = _place_order(sb)
        assert order_b.status_code == 201
        _mock_pay(sb, order_b.json(), "CANCELLED")
    finally:
        _psql(
            "UPDATE inventory_reservations SET status='released', released_at=now() "
            f"WHERE status='active' AND product_variant_id='{vid}'"
        )
        _set_stock(vid, original)
        sa.delete(f"{API}/cart")
        sb.delete(f"{API}/cart")


# ---------------- released reservation cannot be committed directly ----------------

def test_released_reservation_needs_reacquisition(abaya):
    """FAILED payment releases the reservation. A later new Prepare+Complete
    sequence must reacquire stock (replacement row), never commit the
    released row directly."""
    pid, vid = abaya["product_id"], abaya["variant_id"]
    s = _guest_with_cart(pid, vid, 1)
    stock_before = _stock(vid)
    order = _place_order(s).json()
    failed = _mock_pay(s, order, "FAILED").json()
    assert failed["payment_status"] == "failed"
    assert _res_rows(order["order_number"]) == ["released:1:-"]
    assert _stock(vid) == stock_before
    # new payment attempt (new CLICK transaction) via simulator
    mtid = order["payment"]["merchant_trans_id"]
    retry = _simulate(mtid, "SUCCESS").json()
    assert retry["payment_status"] == "paid"
    rows = _res_rows(order["order_number"])
    assert rows[0] == "released:1:-", "released row stays historically released"
    assert rows[1].startswith("committed:1:"), "replacement committed via reacquisition"
    assert _stock(vid) == stock_before - 1, "decremented exactly once across both attempts"
    s.delete(f"{API}/cart")


# ---------------- regressions on the normal paths ----------------

def test_normal_active_commit_has_no_replacement(abaya):
    pid, vid = abaya["product_id"], abaya["variant_id"]
    s = _guest_with_cart(pid, vid, 1)
    stock_before = _stock(vid)
    order = _place_order(s).json()
    paid = _mock_pay(s, order, "SUCCESS").json()
    assert paid["payment_status"] == "paid"
    rows = _res_rows(order["order_number"])
    assert rows == ["committed:1:-"], "normal path: direct commit, no replacement rows"
    assert _stock(vid) == stock_before - 1
    # duplicate complete via simulator stays exactly-once
    _simulate(order["payment"]["merchant_trans_id"], "DUPLICATE_COMPLETE")
    assert _stock(vid) == stock_before - 1
    s.delete(f"{API}/cart")


def test_reconciliation_state_centralized():
    from payments.service import PAYMENT_STATUSES
    from checkout import service as cs
    assert "reconciliation_required" in PAYMENT_STATUSES
    assert cs.ORDER_STATUS_PAYMENT_REVIEW == "payment_review"
    assert cs.ORDER_PAYMENT_STATE_REVIEW == "review"


def test_expiry_job_entrypoint_runs():
    import subprocess as sp
    out = sp.run(
        ["python3", "-m", "jobs.expire_reservations"],
        cwd="/app/backend", capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 0, out.stderr
