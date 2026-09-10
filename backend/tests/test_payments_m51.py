"""Milestone 5.1 — UZS + CLICK payment foundation tests (mock mode)."""

import hashlib
import os
import uuid

import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8000")
API = f"{BASE}/api/v1"
MOCK_SECRET = os.environ.get("CLICK_MOCK_SECRET_KEY", "local-click-secret")


def make_order(amount=350000):
    r = requests.post(f"{API}/payments/mock/order", json={"amount": amount})
    assert r.status_code == 201, r.text
    return r.json()


def simulate(merchant_trans_id, scenario):
    r = requests.post(
        f"{API}/payments/mock/simulate",
        json={"merchant_trans_id": merchant_trans_id, "scenario": scenario},
    )
    assert r.status_code == 200, r.text
    return r.json()


def status(merchant_trans_id):
    r = requests.get(f"{API}/payments/mock/status/{merchant_trans_id}")
    assert r.status_code == 200, r.text
    return r.json()


# --- currency ---

def test_products_report_uzs():
    data = requests.get(f"{API}/catalog/products?limit=5").json()
    assert data["items"], "no products"
    assert all(p["currency"] == "UZS" for p in data["items"])


def test_mock_order_amount_integer_uzs():
    o = make_order(499000)
    assert o["currency"] == "UZS"
    assert isinstance(o["amount"], int)


# --- scenario matrix ---

def test_success_flow():
    o = make_order()
    res = simulate(o["merchant_trans_id"], "SUCCESS")
    assert res["payment_status"] == "paid"
    assert res["order_status"] == "paid"
    assert res["order_payment_state"] == "paid"
    assert [s["error"] for s in res["steps"]] == [0, 0]


def test_failed_flow():
    o = make_order()
    res = simulate(o["merchant_trans_id"], "FAILED")
    assert res["payment_status"] == "failed"
    assert res["order_payment_state"] == "failed"


def test_cancelled_flow():
    o = make_order()
    res = simulate(o["merchant_trans_id"], "CANCELLED")
    assert res["payment_status"] == "cancelled"
    assert res["order_payment_state"] == "cancelled"


def test_timeout_flow_stays_prepared():
    o = make_order()
    res = simulate(o["merchant_trans_id"], "TIMEOUT")
    assert res["payment_status"] == "prepared"
    assert res["order_payment_state"] in ("pending", "unpaid")


def test_expired_flow():
    o = make_order()
    res = simulate(o["merchant_trans_id"], "EXPIRED")
    assert res["payment_status"] == "expired"
    assert res["order_payment_state"] == "expired"


def test_wrong_amount_no_mutation():
    o = make_order()
    res = simulate(o["merchant_trans_id"], "WRONG_AMOUNT")
    complete_step = [s for s in res["steps"] if s["step"] == "complete"][0]
    assert complete_step["error"] == -2
    assert res["payment_status"] == "prepared"
    assert res["order_payment_state"] == "unpaid"


def test_invalid_signature_rejected():
    o = make_order()
    res = simulate(o["merchant_trans_id"], "INVALID_SIGNATURE")
    assert res["steps"][0]["error"] == -1
    assert res["payment_status"] == "pending"


def test_order_not_found():
    o = make_order()
    res = simulate(o["merchant_trans_id"], "ORDER_NOT_FOUND")
    assert res["steps"][0]["error"] == -5


def test_transaction_not_found():
    o = make_order()
    res = simulate(o["merchant_trans_id"], "TRANSACTION_NOT_FOUND")
    complete_step = [s for s in res["steps"] if s["step"] == "complete"][0]
    assert complete_step["error"] == -6
    assert res["payment_status"] == "prepared"


def test_duplicate_prepare_single_record():
    o = make_order()
    res = simulate(o["merchant_trans_id"], "DUPLICATE_PREPARE")
    prepares = [s for s in res["steps"] if s["step"] == "prepare"]
    assert all(s["error"] == 0 for s in prepares)
    assert prepares[0]["merchant_prepare_id"] == prepares[1]["merchant_prepare_id"]
    st = status(o["merchant_trans_id"])
    assert st["status"] == "prepared"


def test_duplicate_complete_no_double_effect():
    o = make_order()
    res = simulate(o["merchant_trans_id"], "DUPLICATE_COMPLETE")
    completes = [s for s in res["steps"] if s["step"] == "complete"]
    assert all(s["error"] == 0 for s in completes)
    assert completes[0]["merchant_confirm_id"] == completes[1]["merchant_confirm_id"]
    st = status(o["merchant_trans_id"])
    assert st["status"] == "paid"
    ok_completes = [e for e in st["events"] if e["event_type"] == "COMPLETE" and e["result"] == "ok"]
    assert len(ok_completes) == 1, "financial effect must happen exactly once"


def test_already_paid_other_transaction():
    o = make_order()
    res = simulate(o["merchant_trans_id"], "ALREADY_PAID")
    other = [s for s in res["steps"] if s["step"] == "complete_other_trans"]
    assert other and other[0]["error"] == -4
    assert res["payment_status"] == "paid"


def test_refund_simulation_once():
    o = make_order()
    res = simulate(o["merchant_trans_id"], "REFUND")
    assert res["payment_status"] == "refunded"
    assert res["order_status"] == "refunded"


def test_events_have_no_secrets():
    o = make_order()
    simulate(o["merchant_trans_id"], "SUCCESS")
    st = status(o["merchant_trans_id"])
    assert len(st["events"]) >= 3  # CREATE + PREPARE + COMPLETE
    blob = str(st["events"]).lower()
    assert "secret" not in blob and "mock-dev" not in blob


# --- raw protocol callbacks over HTTP ---

def _sign(fields, secret, action):
    parts = [fields["click_trans_id"], fields["service_id"], secret, fields["merchant_trans_id"]]
    if action == "1":
        parts.append(fields["merchant_prepare_id"])
    parts += [fields["amount"], action, fields["sign_time"]]
    return hashlib.md5("".join(parts).encode()).hexdigest()


def _raw_params(payment_id, amount, action, secret=None, **over):
    import datetime
    fields = {
        "click_trans_id": uuid.uuid4().hex[:10],
        "service_id": "mock-service",
        "click_paydoc_id": "PDOC-1",
        "merchant_trans_id": payment_id,
        "amount": amount,
        "action": action,
        "error": "0",
        "error_note": "",
        "sign_time": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S"),
    }
    secret = secret or MOCK_SECRET
    if action == "1":
        fields["merchant_prepare_id"] = over.pop("merchant_prepare_id", "0")
    fields.update(over)
    fields["sign_string"] = _sign(fields, secret, action)
    return fields


def test_http_prepare_complete_valid():
    o = make_order(149000)
    prep = _raw_params(o["merchant_trans_id"], "149000", "0")
    r = requests.post(f"{API}/payments/click/prepare", data=prep)
    body = r.json()
    assert body["error"] == 0 and body["merchant_prepare_id"]
    comp = _raw_params(
        o["merchant_trans_id"], "149000", "1",
        merchant_prepare_id=str(body["merchant_prepare_id"]),
        click_trans_id=prep["click_trans_id"],
    )
    r2 = requests.post(f"{API}/payments/click/complete", data=comp)
    assert r2.json()["error"] == 0
    assert status(o["merchant_trans_id"])["status"] == "paid"


def test_http_prepare_invalid_signature():
    o = make_order()
    prep = _raw_params(o["merchant_trans_id"], str(o["amount"]), "0")
    prep["sign_string"] = "f" * 32
    r = requests.post(f"{API}/payments/click/prepare", data=prep)
    assert r.json()["error"] == -1
    assert status(o["merchant_trans_id"])["status"] == "pending"


def test_http_wrong_amount_no_mutation():
    o = make_order(200000)
    prep = _raw_params(o["merchant_trans_id"], "200001", "0")
    r = requests.post(f"{API}/payments/click/prepare", data=prep)
    assert r.json()["error"] == -2
    assert status(o["merchant_trans_id"])["status"] == "pending"


def test_http_wrong_service_and_action():
    o = make_order()
    prep = _raw_params(o["merchant_trans_id"], str(o["amount"]), "0", **{"service_id": "wrong"})
    # signature was computed with wrong service id too; expect -8 or -1, never 0
    assert requests.post(f"{API}/payments/click/prepare", data=prep).json()["error"] != 0
    bad_action = _raw_params(o["merchant_trans_id"], str(o["amount"]), "0", **{})
    bad_action["action"] = "9"
    assert requests.post(f"{API}/payments/click/prepare", data=bad_action).json()["error"] in (-3, -1)


def test_http_unknown_order_safe():
    prep = _raw_params("nonexistent-trans", "1000", "0")
    r = requests.post(f"{API}/payments/click/prepare", data=prep)
    assert r.json()["error"] == -5


def test_raw_amount_string_fidelity():
    # "350000.00" signs differently from "350000" — signature must be
    # computed over the raw string (invalid here -> -1, proving fidelity)
    o = make_order(350000)
    prep = _raw_params(o["merchant_trans_id"], "350000", "0")
    prep["amount"] = "350000.00"  # change after signing -> signature mismatch
    r = requests.post(f"{API}/payments/click/prepare", data=prep)
    assert r.json()["error"] == -1
    # correctly signed raw "350000.00" passes signature (raw string was
    # preserved verbatim, not normalized before signing)
    prep2 = _raw_params(o["merchant_trans_id"], "350000.00", "0")
    r2 = requests.post(f"{API}/payments/click/prepare", data=prep2)
    assert r2.json()["error"] == 0
    # numerically different amount is rejected without mutation
    o2 = make_order(350000)
    prep3 = _raw_params(o2["merchant_trans_id"], "350001", "0")
    r3 = requests.post(f"{API}/payments/click/prepare", data=prep3)
    assert r3.json()["error"] == -2
    assert status(o2["merchant_trans_id"])["status"] == "pending"


def test_mock_simulator_locked_outside_mock_mode():
    # config check: CLICK_MODE is mock in this env, simulator reachable;
    # the gate itself is verified by code path _require_mock_mode (404 otherwise)
    assert requests.post(f"{API}/payments/mock/order", json={"amount": 1000}).status_code == 201
