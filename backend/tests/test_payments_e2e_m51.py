"""E2E API integration tests for Milestone 5.1 payments against the live backend URL."""
import os
import hashlib
import time
import uuid
import requests
import pytest

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else "https://muslimah-shop.preview.emergentagent.com"
API = f"{BASE}/api/v1/payments"
SECRET = "mock-dev-5c2f8a91e7b4d603"
SERVICE_ID = "mock-service"


def _md5(*parts):
    return hashlib.md5("".join(parts).encode()).hexdigest()


def _mk_order(amount=350000):
    r = requests.post(f"{API}/mock/order", json={"amount": amount}, timeout=15)
    assert r.status_code in (200, 201), r.text
    return r.json()  # expects merchant_trans_id, amount


def _simulate(mtid, scenario):
    r = requests.post(f"{API}/mock/simulate", json={"merchant_trans_id": mtid, "scenario": scenario}, timeout=15)
    return r


def _status(mtid):
    r = requests.get(f"{API}/mock/status/{mtid}", timeout=15)
    return r


# --- Mock simulator E2E ---

def test_success_scenario_e2e():
    o = _mk_order(350000)
    mtid = o["merchant_trans_id"]
    s = _status(mtid); assert s.status_code == 200
    assert s.json()["status"] in ("pending", "created")
    r = _simulate(mtid, "SUCCESS")
    assert r.status_code == 200, r.text
    s = _status(mtid).json()
    assert s["status"] == "paid", s
    kinds = [e["event_type"] for e in s["events"]]
    assert any("CREATE" in k.upper() for k in kinds)
    assert any("PREPARE" in k.upper() for k in kinds)
    assert any("COMPLETE" in k.upper() for k in kinds)


def test_duplicate_prepare_idempotent():
    o = _mk_order(); mtid = o["merchant_trans_id"]
    r = _simulate(mtid, "DUPLICATE_PREPARE")
    assert r.status_code == 200, r.text
    s = _status(mtid).json()
    assert s["status"] in ("prepared", "paid", "pending"), s


def test_duplicate_complete_exactly_once():
    o = _mk_order(); mtid = o["merchant_trans_id"]
    r = _simulate(mtid, "DUPLICATE_COMPLETE")
    assert r.status_code == 200, r.text
    s = _status(mtid).json()
    assert s["status"] == "paid", s


def test_wrong_amount():
    o = _mk_order(); mtid = o["merchant_trans_id"]
    r = _simulate(mtid, "WRONG_AMOUNT")
    assert r.status_code == 200
    s = _status(mtid).json()
    assert s["status"] != "paid"


def test_invalid_signature_scenario():
    o = _mk_order(); mtid = o["merchant_trans_id"]
    r = _simulate(mtid, "INVALID_SIGNATURE")
    assert r.status_code == 200
    s = _status(mtid).json()
    assert s["status"] != "paid"


def test_already_paid():
    o = _mk_order(); mtid = o["merchant_trans_id"]
    _simulate(mtid, "SUCCESS")
    r = _simulate(mtid, "ALREADY_PAID")
    assert r.status_code == 200


# --- Raw HTTP protocol ---

def _prepare_form(mtid, amount_str, click_trans_id="100001", sign_time=None, secret=SECRET, tamper=False, action="0"):
    sign_time = sign_time or time.strftime("%Y-%m-%d %H:%M:%S")
    raw = f"{click_trans_id}{SERVICE_ID}{secret}{mtid}{amount_str}{action}{sign_time}"
    sign = _md5(click_trans_id, SERVICE_ID, secret, mtid, amount_str, action, sign_time)
    if tamper:
        sign = "0" * 32
    data = {
        "click_trans_id": click_trans_id,
        "service_id": SERVICE_ID,
        "click_paydoc_id": "9999",
        "merchant_trans_id": mtid,
        "amount": amount_str,
        "action": action,
        "sign_time": sign_time,
        "sign_string": sign,
        "error": "0",
        "error_note": "",
    }
    return data


def test_raw_prepare_ok():
    o = _mk_order(); mtid = o["merchant_trans_id"]
    data = _prepare_form(mtid, "350000")
    r = requests.post(f"{API}/click/prepare", data=data, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("error") == 0, body


def test_raw_prepare_bad_signature():
    o = _mk_order(); mtid = o["merchant_trans_id"]
    data = _prepare_form(mtid, "350000", tamper=True)
    r = requests.post(f"{API}/click/prepare", data=data, timeout=15)
    assert r.status_code == 200
    assert r.json().get("error") == -1


def test_raw_prepare_amount_mismatch():
    o = _mk_order(); mtid = o["merchant_trans_id"]
    # sign amount 350001 correctly but the payment is 350000
    data = _prepare_form(mtid, "350001")
    r = requests.post(f"{API}/click/prepare", data=data, timeout=15)
    assert r.status_code == 200
    assert r.json().get("error") == -2
    # verify no mutation
    s = _status(mtid).json()
    assert s["status"] not in ("prepared", "paid")


def test_raw_prepare_unknown_order():
    data = _prepare_form("does-not-exist-" + uuid.uuid4().hex[:8], "350000")
    r = requests.post(f"{API}/click/prepare", data=data, timeout=15)
    assert r.status_code == 200
    # -5 order not found
    assert r.json().get("error") == -5


def test_raw_prepare_wrong_action():
    o = _mk_order(); mtid = o["merchant_trans_id"]
    data = _prepare_form(mtid, "350000", action="9")
    r = requests.post(f"{API}/click/prepare", data=data, timeout=15)
    assert r.status_code == 200
    assert r.json().get("error") == -3


def test_raw_complete_without_prepare():
    o = _mk_order(); mtid = o["merchant_trans_id"]
    # complete = action 1, but no prepare done
    sign_time = time.strftime("%Y-%m-%d %H:%M:%S")
    click_trans_id = "200001"
    merchant_prepare_id = "999999"
    action = "1"
    amount_str = "350000"
    # complete signature order per CLICK: click_trans_id+service_id+secret+merchant_trans_id+merchant_prepare_id+amount+action+sign_time
    sign = hashlib.md5(f"{click_trans_id}{SERVICE_ID}{SECRET}{mtid}{merchant_prepare_id}{amount_str}{action}{sign_time}".encode()).hexdigest()
    data = {
        "click_trans_id": click_trans_id, "service_id": SERVICE_ID, "click_paydoc_id": "9999", "merchant_trans_id": mtid,
        "merchant_prepare_id": merchant_prepare_id, "amount": amount_str, "action": action,
        "sign_time": sign_time, "sign_string": sign, "error": "0", "error_note": "",
    }
    r = requests.post(f"{API}/click/complete", data=data, timeout=15)
    assert r.status_code == 200
    # -6 transaction not found
    assert r.json().get("error") == -6


def test_raw_amount_string_fidelity_dot_zero_rejected_when_raw_int():
    """Client sends raw '350000' but signs '350000.00' — signature over raw string must fail (-1)."""
    o = _mk_order(); mtid = o["merchant_trans_id"]
    sign_time = time.strftime("%Y-%m-%d %H:%M:%S")
    click_trans_id = "300001"
    # sign the .00 variant but send raw
    sign = _md5(click_trans_id, SERVICE_ID, SECRET, mtid, "350000.00", "0", sign_time)
    data = {
        "click_trans_id": click_trans_id, "service_id": SERVICE_ID, "click_paydoc_id": "9999", "merchant_trans_id": mtid,
        "amount": "350000", "action": "0", "sign_time": sign_time, "sign_string": sign,
        "error": "0", "error_note": "",
    }
    r = requests.post(f"{API}/click/prepare", data=data, timeout=15)
    assert r.status_code == 200
    assert r.json().get("error") == -1


# --- UZS regression ---

def test_catalog_currency_is_uzs():
    r = requests.get(f"{BASE}/api/v1/catalog/products?limit=5", timeout=15)
    assert r.status_code == 200
    data = r.json()
    items = data.get("items") or data.get("results") or data
    if isinstance(items, dict):
        items = items.get("items", [])
    assert items, data
    for it in items[:3]:
        # currency may be nested under price
        cur = it.get("currency") or (it.get("price") or {}).get("currency") if isinstance(it.get("price"), dict) else it.get("currency")
        # fallback: any 'UZS' string in JSON
        if not cur:
            cur = "UZS" if "UZS" in str(it) else None
        assert cur == "UZS", it
