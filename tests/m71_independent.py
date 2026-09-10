"""Independent M7.1 verification (separate from pytest suite).
Uses same PSQL + HTTP approach but re-implemented to independently confirm."""
import os, subprocess, uuid, requests, sys

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://muslimah-shop.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api/v1"
DB_URL = "postgresql://muslimah:muslimah_dev_pass@localhost:5432/muslimah_cantik"

ADDR = {"recipient_name": "Test User", "phone": "+998901112233",
        "address_line_1": "1 Test Street", "city": "Tashkent",
        "state_province": "Tashkent", "postal_code": "100000", "country_code": "UZ"}

def psql(sql):
    o = subprocess.run(["psql", DB_URL, "-tA", "-c", sql], capture_output=True, text=True)
    return o.stdout.strip()

def stock(vid): return int(psql(f"SELECT stock_quantity FROM product_variants WHERE id='{vid}'"))
def set_stock(vid, n): psql(f"UPDATE product_variants SET stock_quantity={n} WHERE id='{vid}'")
def rows(order_number):
    out = psql("SELECT r.status || ':' || r.quantity || ':' || COALESCE(r.reacquired_from,'-') "
               "FROM inventory_reservations r JOIN orders o ON o.id=r.order_id "
               f"WHERE o.order_number='{order_number}' ORDER BY r.created_at, r.id")
    return [l for l in out.splitlines() if l]

def backdate(order_number):
    psql("UPDATE inventory_reservations SET expires_at=now()-interval '1 minute' "
         f"WHERE status='active' AND order_id=(SELECT id FROM orders WHERE order_number='{order_number}')")

def product(slug):
    return requests.get(f"{API}/catalog/products/{slug}").json()

def guest_cart(pid, vid, qty=1):
    s = requests.Session()
    r = s.post(f"{API}/cart/items", json={"product_id": pid, "variant_id": vid, "quantity": qty})
    assert r.status_code == 201, r.text
    return s

def place_order(s):
    r = s.post(f"{API}/checkout/orders", json={
        "idempotency_key": uuid.uuid4().hex, "shipping_method": "standard",
        "locale": "en", "email": "guest@example.com", "address": ADDR})
    return r

def pay(s, order_resp, scenario):
    return s.post(f"{API}/payments/mock/pay", json={
        "merchant_trans_id": order_resp["payment"]["merchant_trans_id"],
        "order_number": order_resp["order_number"], "scenario": scenario,
        "access_token": order_resp.get("access_token")})

def simulate(mtid, scenario):
    return requests.post(f"{API}/payments/mock/simulate",
                         json={"merchant_trans_id": mtid, "scenario": scenario})

def sweep(s):
    return s.post(f"{API}/checkout/quote", json={"shipping_method": "standard"})

P = product("abaya-classic-black")
V = next(x for x in P["variants"] if x["sku"] == "ACBK-BLK-M")
PID, VID = P["id"], V["id"]
ORIG = stock(VID)
print(f"Variant {VID} original stock: {ORIG}")

passed, failed = [], []
def check(cond, msg):
    (passed if cond else failed).append(msg)
    print(("PASS: " if cond else "FAIL: ") + msg)

try:
    # ============= SCENARIO 1: RACE =============
    print("\n=== SCENARIO 1: RACE (stock=1) ===")
    set_stock(VID, 1)
    sA = guest_cart(PID, VID)
    rA = place_order(sA)
    assert rA.status_code == 201, f"A order failed: {rA.status_code} {rA.text}"
    oA = rA.json()
    prep = pay(sA, oA, "TIMEOUT").json()
    check(prep.get("payment_status") == "prepared", f"A TIMEOUT prepared (got {prep.get('payment_status')})")

    sB = guest_cart(PID, VID)
    blocked = place_order(sB)
    check(blocked.status_code == 409, f"B blocked while A active (got {blocked.status_code})")

    backdate(oA["order_number"])
    sw = sweep(sB)
    check(sw.status_code == 200, f"quote sweep after backdate (got {sw.status_code})")
    check(rows(oA["order_number"]) == ["expired:1:-"], f"A row expired only: {rows(oA['order_number'])}")

    oB_resp = place_order(sB)
    check(oB_resp.status_code == 201, f"B places order (got {oB_resp.status_code})")
    oB = oB_resp.json()

    late = pay(sA, oA, "SUCCESS").json()
    complete_step = next((s for s in late.get("steps", []) if s.get("step") == "complete"), None)
    check(complete_step and complete_step.get("error") == -7, f"A complete error=-7 (got {complete_step})")
    check(late.get("payment_status") == "reconciliation_required", f"A payment_status (got {late.get('payment_status')})")
    check(late.get("order_status") == "payment_review", f"A order_status (got {late.get('order_status')})")
    check(late.get("order_payment_state") == "review", f"A order_payment_state (got {late.get('order_payment_state')})")
    check(stock(VID) == 1, f"stock still 1 (got {stock(VID)})")
    check(rows(oA["order_number"]) == ["expired:1:-"], f"no replacement row: {rows(oA['order_number'])}")
    cA = sA.get(f"{API}/cart").json()
    check(cA.get("item_count") == 1, f"A cart preserved item_count=1 (got {cA.get('item_count')})")

    late2 = pay(sA, oA, "SUCCESS").json()
    check(late2.get("payment_status") == "reconciliation_required", "repeat idempotent still reconciliation_required")
    check(stock(VID) == 1, f"stock still 1 after repeat (got {stock(VID)})")

    paidB = pay(sB, oB, "SUCCESS").json()
    check(paidB.get("payment_status") == "paid", f"B paid (got {paidB.get('payment_status')})")
    check(stock(VID) == 0, f"stock=0 after B paid (got {stock(VID)})")

    late3 = pay(sA, oA, "SUCCESS").json()
    check(late3.get("payment_status") == "reconciliation_required", "A retry still reconciliation_required")
    check(stock(VID) == 0, f"stock stays 0 (got {stock(VID)})")

    # cleanup A's cart
    sA.delete(f"{API}/cart"); sB.delete(f"{API}/cart")

    # ============= SCENARIO 2: REACQUISITION =============
    print("\n=== SCENARIO 2: REACQUISITION (stock=2) ===")
    set_stock(VID, 2)
    sA2 = guest_cart(PID, VID)
    rA2 = place_order(sA2); assert rA2.status_code == 201, rA2.text
    oA2 = rA2.json()
    pay(sA2, oA2, "TIMEOUT")
    backdate(oA2["order_number"])
    sX = guest_cart(PID, VID)
    sweep(sX)
    check(rows(oA2["order_number"]) == ["expired:1:-"], "A2 expired only before late")
    check(stock(VID) == 2, f"stock still 2 (expiry doesn't dec) (got {stock(VID)})")

    late = pay(sA2, oA2, "SUCCESS").json()
    check(late.get("payment_status") == "paid", f"A2 reacquired paid (got {late.get('payment_status')})")
    check(stock(VID) == 1, f"A2 stock=1 (got {stock(VID)})")
    r2 = rows(oA2["order_number"])
    check(len(r2) == 2, f"A2 has 2 rows: {r2}")
    check(r2[0] == "expired:1:-", f"A2 row0 expired unchanged: {r2}")
    check(r2[1].startswith("committed:1:") and r2[1] != "committed:1:-", f"A2 row1 committed with reacquired_from: {r2}")
    c2 = sA2.get(f"{API}/cart").json()
    check(c2.get("item_count") == 0, f"A2 cart cleared (got {c2.get('item_count')})")

    again = pay(sA2, oA2, "SUCCESS").json()
    check(again.get("payment_status") == "paid", "A2 repeat still paid")
    check(stock(VID) == 1, "A2 no duplicate decrement")
    check(rows(oA2["order_number"]) == r2, "A2 no new reservation row on repeat")

    sA2.delete(f"{API}/cart"); sX.delete(f"{API}/cart")

    # ============= SCENARIO 3: RELEASED-ROW =============
    print("\n=== SCENARIO 3: RELEASED-ROW ===")
    sA3 = guest_cart(PID, VID)
    stock_b = stock(VID)
    rA3 = place_order(sA3); assert rA3.status_code == 201, rA3.text
    oA3 = rA3.json()
    f_r = pay(sA3, oA3, "FAILED").json()
    check(f_r.get("payment_status") == "failed", f"A3 FAILED (got {f_r.get('payment_status')})")
    check(rows(oA3["order_number"]) == ["released:1:-"], f"A3 released: {rows(oA3['order_number'])}")
    check(stock(VID) == stock_b, f"A3 stock unchanged after fail")

    mtid = oA3["payment"]["merchant_trans_id"]
    retry = simulate(mtid, "SUCCESS").json()
    check(retry.get("payment_status") == "paid", f"A3 retry paid (got {retry.get('payment_status')})")
    r3 = rows(oA3["order_number"])
    check(r3[0] == "released:1:-", f"A3 released unchanged: {r3}")
    check(r3[1].startswith("committed:1:") and r3[1] != "committed:1:-", f"A3 replacement committed: {r3}")
    check(stock(VID) == stock_b - 1, f"A3 stock dec once (got {stock(VID)}, expected {stock_b-1})")
    sA3.delete(f"{API}/cart")

except Exception as e:
    import traceback; traceback.print_exc()
finally:
    print(f"\n=== RESTORING stock to {ORIG} ===")
    # release any active reservations for this variant
    psql(f"UPDATE inventory_reservations SET status='released', released_at=now() "
         f"WHERE status='active' AND product_variant_id='{VID}'")
    set_stock(VID, ORIG)
    print(f"Final stock: {stock(VID)}")
    print(f"\n=== TOTAL: {len(passed)} passed, {len(failed)} failed ===")
    for f in failed: print(f"  FAILED: {f}")
    sys.exit(0 if not failed else 1)
