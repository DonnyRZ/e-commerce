"""M7.1 race + reacquisition + released-row scenarios via HTTP + psql."""
import os
import uuid
import subprocess
import requests
import json
import sys

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://muslimah-shop.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api/v1"
PSQL = ["psql", "postgresql://muslimah:muslimah_dev_pass@localhost:5432/muslimah_cantik", "-tAc"]
VARIANT_SKU = "ACBK-BLK-M"
VARIANT_ID = "1d3292f36bde43178b319fc7d3c57959"
PRODUCT_ID = "d9b35094b2a842f8937167e79bb2b896"

def psql(sql):
    r = subprocess.run(PSQL + [sql], capture_output=True, text=True)
    return r.stdout.strip()

def set_stock(n):
    psql(f"UPDATE product_variants SET stock_quantity={n} WHERE id='{VARIANT_ID}';")

def get_stock():
    return int(psql(f"SELECT stock_quantity FROM product_variants WHERE id='{VARIANT_ID}';"))

def new_session():
    s = requests.Session()
    # bootstrap guest session cookie
    s.get(f"{API}/cart", timeout=10)
    return s

def add_and_checkout(s, qty=1, scenario=None):
    """Add variant to cart, create order, return (order_number, resp_json)."""
    r = s.post(f"{API}/cart/items", json={"product_id": PRODUCT_ID, "variant_id": VARIANT_ID, "quantity": qty}, timeout=10)
    assert r.status_code in (200, 201), f"cart add failed: {r.status_code} {r.text}"
    idem = str(uuid.uuid4())
    payload = {
        "idempotency_key": idem,
        "shipping_method": "standard",
        "email": f"test+{idem[:8]}@example.com",
        "address": {
            "recipient_name": "Test User", "phone": "+998900000000",
            "address_line_1": "Test 1", "city": "Tashkent",
            "state_province": "Tashkent", "postal_code": "100000",
            "country_code": "UZ"
        },
    }
    r = s.post(f"{API}/checkout/orders", json=payload,
               headers={"Idempotency-Key": idem}, timeout=15)
    return r

def mock_pay(s, order_number, scenario):
    # first prepare via mock/pay
    r = s.post(f"{API}/payments/mock/pay",
               json={"order_number": order_number, "scenario": scenario}, timeout=15)
    return r

def print_res_rows(order_number, label=""):
    rows = psql(f"""SELECT id, status, reacquired_from FROM inventory_reservations
                    WHERE order_id=(SELECT id FROM orders WHERE order_number='{order_number}')
                    ORDER BY created_at;""")
    print(f"  [reservations {label}]:\n{rows}")
    return rows

def order_state(order_number):
    return psql(f"""SELECT status || '|' || COALESCE(payment_state,'') FROM orders WHERE order_number='{order_number}';""")

results = {"passed": [], "failed": []}
def check(cond, msg):
    if cond:
        print(f"  PASS: {msg}")
        results["passed"].append(msg)
    else:
        print(f"  FAIL: {msg}")
        results["failed"].append(msg)

ORIGINAL_STOCK = get_stock()
print(f"Original stock: {ORIGINAL_STOCK}")

try:
    # ============= SCENARIO 1: RACE / RECONCILIATION_REQUIRED =============
    print("\n=== SCENARIO 1: RACE (reconciliation_required, stock=1) ===")
    set_stock(1)

    sA = new_session()
    rA = add_and_checkout(sA)
    assert rA.status_code == 201, f"A order failed: {rA.status_code} {rA.text}"
    order_A = rA.json()["order_number"]
    print(f"A order: {order_A}")

    # Prepare payment (TIMEOUT scenario -> no complete)
    pr = mock_pay(sA, order_A, "TIMEOUT")
    print(f"A mock/pay TIMEOUT: {pr.status_code} {pr.json().get('payment_status')}")

    # Capture merchant_trans_id + access_token for later SUCCESS reuse
    pay_data = pr.json()
    merchant_trans_id = pay_data.get("merchant_trans_id")
    access_token = pay_data.get("access_token")
    print(f"  merchant_trans_id={merchant_trans_id}, access_token={access_token}")

    # Guest B tries same variant -> should be rejected 409
    sB = new_session()
    rB1 = sB.post(f"{API}/cart/items", json={"product_id": PRODUCT_ID, "variant_id": VARIANT_ID, "quantity": 1}, timeout=10)
    # cart add may succeed; checkout should 409
    idem = str(uuid.uuid4())
    payload = {"idempotency_key": idem, "shipping_method": "standard",
               "email": "b@example.com",
               "address": {"recipient_name": "B", "phone": "+998900000001",
                           "address_line_1": "L", "city": "T", "state_province": "T",
                           "postal_code": "100000", "country_code": "UZ"}}
    rB_co = sB.post(f"{API}/checkout/orders", json=payload,
                    headers={"Idempotency-Key": idem}, timeout=15)
    check(rB_co.status_code == 409, f"B rejected while A reservation active (got {rB_co.status_code})")

    # Backdate A's reservation
    psql(f"""UPDATE inventory_reservations SET expires_at=now() - interval '1 minute'
             WHERE status='active' AND order_id=(SELECT id FROM orders WHERE order_number='{order_A}');""")

    # Trigger lazy sweep via B's quote
    q = sB.post(f"{API}/checkout/quote", json={}, timeout=15)
    print(f"B quote after backdate: {q.status_code}")

    # Verify A row is now expired
    a_status = psql(f"""SELECT status FROM inventory_reservations
                        WHERE order_id=(SELECT id FROM orders WHERE order_number='{order_A}');""")
    check(a_status == "expired", f"A reservation expired after sweep (got '{a_status}')")

    # B places order -> should succeed 201
    idem = str(uuid.uuid4())
    payload["idempotency_key"] = idem
    rB_co2 = sB.post(f"{API}/checkout/orders", json=payload,
                     headers={"Idempotency-Key": idem}, timeout=15)
    check(rB_co2.status_code == 201, f"B order after A expire (got {rB_co2.status_code} {rB_co2.text[:200]})")
    order_B = rB_co2.json()["order_number"] if rB_co2.status_code == 201 else None
    print(f"B order: {order_B}")

    # Delayed SUCCESS for A
    pr_late = mock_pay(sA, order_A, "SUCCESS")
    print(f"A late SUCCESS: {pr_late.status_code} body={pr_late.text[:400]}")
    body = pr_late.json()
    check(body.get("payment_status") == "reconciliation_required",
          f"A payment_status=reconciliation_required (got {body.get('payment_status')})")
    check(body.get("order_status") == "payment_review",
          f"A order_status=payment_review (got {body.get('order_status')})")
    check(body.get("order_payment_state") == "review",
          f"A order_payment_state=review (got {body.get('order_payment_state')})")
    # complete step error == -7
    complete_err = body.get("complete", {}).get("error") if isinstance(body.get("complete"), dict) else body.get("complete_error")
    # search recursively
    def find_err(d):
        if isinstance(d, dict):
            for k, v in d.items():
                if k in ("error", "error_code") and isinstance(v, int):
                    return v
                r = find_err(v)
                if r is not None:
                    return r
        elif isinstance(d, list):
            for i in d:
                r = find_err(i)
                if r is not None:
                    return r
        return None
    err_code = find_err(body)
    check(err_code == -7, f"A complete error == -7 (got {err_code}) body keys={list(body.keys())}")

    check(get_stock() == 1, f"stock still 1 after A late (got {get_stock()})")
    print_res_rows(order_A, "A after late SUCCESS")
    a_rows = psql(f"""SELECT count(*), string_agg(status,',') FROM inventory_reservations
                      WHERE order_id=(SELECT id FROM orders WHERE order_number='{order_A}');""")
    check(a_rows.split("|")[0] == "1" and "expired" in a_rows,
          f"A has exactly 1 expired row (got {a_rows})")

    # Cart A still has 1 item
    cA = sA.get(f"{API}/cart", timeout=10).json()
    a_count = cA.get("item_count") or sum(i["quantity"] for i in cA.get("items", []))
    check(a_count == 1, f"A cart preserved item_count=1 (got {a_count})")

    # Idempotent repeat
    pr_late2 = mock_pay(sA, order_A, "SUCCESS")
    body2 = pr_late2.json()
    check(body2.get("payment_status") == "reconciliation_required", "A repeat late still reconciliation_required")
    check(get_stock() == 1, f"stock still 1 after repeat (got {get_stock()})")

    # B pays SUCCESS -> paid, stock 0
    prB = mock_pay(sB, order_B, "SUCCESS")
    bodyB = prB.json()
    print(f"B SUCCESS: {prB.status_code} status={bodyB.get('payment_status')} order={bodyB.get('order_status')}")
    check(bodyB.get("payment_status") == "paid", f"B paid (got {bodyB.get('payment_status')})")
    check(get_stock() == 0, f"stock=0 after B paid (got {get_stock()})")

    # A retry SUCCESS -> still reconciliation_required
    pr_late3 = mock_pay(sA, order_A, "SUCCESS")
    body3 = pr_late3.json()
    check(body3.get("payment_status") == "reconciliation_required",
          f"A retry after B-paid still reconciliation_required (got {body3.get('payment_status')})")
    check(get_stock() == 0, f"stock stays 0 (got {get_stock()})")

    # ============= SCENARIO 2: REACQUISITION =============
    print("\n=== SCENARIO 2: REACQUISITION (stock=2) ===")
    set_stock(2)
    sA2 = new_session()
    rA2 = add_and_checkout(sA2)
    order_A2 = rA2.json()["order_number"]
    print(f"A2 order: {order_A2}")
    pr = mock_pay(sA2, order_A2, "TIMEOUT")
    print(f"A2 TIMEOUT: {pr.status_code}")

    psql(f"""UPDATE inventory_reservations SET expires_at=now() - interval '1 minute'
             WHERE status='active' AND order_id=(SELECT id FROM orders WHERE order_number='{order_A2}');""")
    # trigger sweep
    sX = new_session()
    sX.post(f"{API}/checkout/quote", json={}, timeout=15)

    pr_late = mock_pay(sA2, order_A2, "SUCCESS")
    body = pr_late.json()
    print(f"A2 late SUCCESS: {pr_late.status_code} status={body.get('payment_status')}")
    check(body.get("payment_status") == "paid", f"A2 reacquired -> paid (got {body.get('payment_status')})")
    check(get_stock() == 1, f"stock=1 after reacquisition (got {get_stock()})")

    rows = psql(f"""SELECT id, status, reacquired_from FROM inventory_reservations
                    WHERE order_id=(SELECT id FROM orders WHERE order_number='{order_A2}')
                    ORDER BY created_at;""")
    print(f"A2 rows:\n{rows}")
    lines = [l for l in rows.split("\n") if l.strip()]
    check(len(lines) == 2, f"A2 has 2 reservation rows (got {len(lines)})")
    has_expired = any("|expired|" in l for l in lines)
    has_committed_reacq = any("|committed|" in l and l.split("|")[-1] != "" for l in lines)
    check(has_expired, "A2 has expired row")
    check(has_committed_reacq, "A2 has committed row with reacquired_from set")

    # Cart cleared
    cA2 = sA2.get(f"{API}/cart", timeout=10).json()
    a2_count = cA2.get("item_count") or sum(i["quantity"] for i in cA2.get("items", []))
    check(a2_count == 0, f"A2 cart cleared after paid (got {a2_count})")

    # Repeat SUCCESS -> zero changes
    stock_before = get_stock()
    row_count_before = len(lines)
    pr_late2 = mock_pay(sA2, order_A2, "SUCCESS")
    check(get_stock() == stock_before, f"stock unchanged after repeat (was {stock_before}, now {get_stock()})")
    rows2 = psql(f"""SELECT count(*) FROM inventory_reservations
                     WHERE order_id=(SELECT id FROM orders WHERE order_number='{order_A2}');""")
    check(int(rows2) == row_count_before, f"row count unchanged (was {row_count_before}, now {rows2})")

    # ============= SCENARIO 3: RELEASED-ROW =============
    print("\n=== SCENARIO 3: RELEASED-ROW ===")
    set_stock(2)
    sA3 = new_session()
    rA3 = add_and_checkout(sA3)
    order_A3 = rA3.json()["order_number"]
    print(f"A3 order: {order_A3}")
    prf = mock_pay(sA3, order_A3, "FAILED")
    print(f"A3 FAILED: {prf.status_code} status={prf.json().get('payment_status')}")
    rel_status = psql(f"""SELECT status FROM inventory_reservations
                          WHERE order_id=(SELECT id FROM orders WHERE order_number='{order_A3}');""")
    check(rel_status == "released", f"A3 reservation released (got {rel_status})")

    # try /simulate SUCCESS
    prs = sA3.post(f"{API}/payments/mock/simulate",
                   json={"order_number": order_A3, "scenario": "SUCCESS"}, timeout=15)
    print(f"A3 simulate SUCCESS: {prs.status_code} body={prs.text[:400]}")
    if prs.status_code != 200:
        # fallback: try mock/pay
        prs = mock_pay(sA3, order_A3, "SUCCESS")
        print(f"A3 mock/pay SUCCESS: {prs.status_code} body={prs.text[:400]}")
    body = prs.json()
    check(body.get("payment_status") == "paid", f"A3 paid via reacquisition (got {body.get('payment_status')})")
    rows3 = psql(f"""SELECT status, reacquired_from FROM inventory_reservations
                     WHERE order_id=(SELECT id FROM orders WHERE order_number='{order_A3}')
                     ORDER BY created_at;""")
    print(f"A3 rows:\n{rows3}")
    lines3 = [l for l in rows3.split("\n") if l.strip()]
    has_released = any(l.startswith("released|") for l in lines3)
    has_committed_reacq = any(l.startswith("committed|") and l.split("|")[1] != "" for l in lines3)
    check(has_released, "A3 has released row unchanged")
    check(has_committed_reacq, "A3 has committed reacquired row")
    check(get_stock() == 1, f"A3 stock decremented once = 1 (got {get_stock()})")

except Exception as e:
    import traceback
    traceback.print_exc()
finally:
    print(f"\n=== RESTORING stock to {ORIGINAL_STOCK} ===")
    set_stock(ORIGINAL_STOCK)
    print(f"Final stock: {get_stock()}")
    print(f"\n=== SUMMARY: {len(results['passed'])} passed, {len(results['failed'])} failed ===")
    for f in results["failed"]:
        print(f"  FAILED: {f}")
    sys.exit(0 if not results["failed"] else 1)
