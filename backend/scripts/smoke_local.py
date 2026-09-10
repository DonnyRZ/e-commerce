"""Repeatable local pre-deployment smoke test.

Run against an isolated PostgreSQL database and a running API server. The
script deliberately exercises the public storefront, guest checkout, payment
state transitions, admin access, refund, and the single-owner route boundary.
"""

from __future__ import annotations

import os
import sys
import uuid

import requests


BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000").rstrip("/")
ADMIN_EMAIL = os.environ.get("SMOKE_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("SMOKE_ADMIN_PASSWORD", "")
TIMEOUT = 10


def check(response: requests.Response, expected: int = 200) -> dict:
    if response.status_code != expected:
        raise AssertionError(
            f"{response.request.method} {response.request.url} -> "
            f"{response.status_code}, expected {expected}: {response.text[:500]}"
        )
    if not response.content:
        return {}
    return response.json()


def post(session: requests.Session, path: str, payload: dict, expected: int = 200):
    return check(session.post(f"{BASE}{path}", json=payload, timeout=TIMEOUT), expected)


def guest_order(scenario: str) -> tuple[requests.Session, dict, dict]:
    session = requests.Session()
    products = check(
        session.get(
            f"{BASE}/api/v1/catalog/products",
            params={"limit": 1, "availability": "in_stock"},
            timeout=TIMEOUT,
        )
    )
    product = products["items"][0]
    detail = check(
        session.get(f"{BASE}/api/v1/catalog/products/{product['slug']}", timeout=TIMEOUT)
    )
    variant = next(v for v in detail["variants"] if v["is_active"] and v["stock_quantity"] > 0)
    cart = post(
        session,
        "/api/v1/cart/items",
        {"product_id": product["id"], "variant_id": variant["id"], "quantity": 1},
        201,
    )
    assert cart["item_count"] == 1
    options = check(session.get(f"{BASE}/api/v1/checkout/options", timeout=TIMEOUT))
    assert options["payment_mode"] == "mock"
    check(
        session.post(
            f"{BASE}/api/v1/checkout/quote",
            json={"shipping_method": "standard"},
            timeout=TIMEOUT,
        )
    )
    order = post(
        session,
        "/api/v1/checkout/orders",
        {
            "idempotency_key": f"smoke-{uuid.uuid4().hex}",
            "shipping_method": "standard",
            "locale": "en",
            "email": f"smoke-{uuid.uuid4().hex[:8]}@example.com",
            "address": {
                "recipient_name": "Smoke Test",
                "phone": "+998901234567",
                "address_line_1": "1 Test Street",
                "city": "Tashkent",
                "state_province": "Tashkent",
                "postal_code": "100000",
                "country_code": "UZ",
            },
        },
        201,
    )
    payment = post(
        session,
        "/api/v1/payments/mock/pay",
        {
            "merchant_trans_id": order["payment"]["merchant_trans_id"],
            "order_number": order["order_number"],
            "access_token": order["access_token"],
            "scenario": scenario,
        },
    )
    tracked = check(
        session.get(
            f"{BASE}/api/v1/orders/track",
            params={"order_number": order["order_number"], "token": order["access_token"]},
            timeout=TIMEOUT,
        )
    )
    assert tracked["payment_state"] == payment["order_payment_state"]
    return session, order, payment


def main() -> int:
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        raise SystemExit("SMOKE_ADMIN_EMAIL and SMOKE_ADMIN_PASSWORD are required")

    public = requests.Session()
    ready = check(public.get(f"{BASE}/api/ready", timeout=TIMEOUT))
    assert all(value == "up" for value in ready["checks"].values()), ready
    check(public.get(f"{BASE}/api/status", timeout=TIMEOUT), 404)
    check(public.get(f"{BASE}/api/v1/seller/dashboard", timeout=TIMEOUT), 404)
    assert check(public.get(f"{BASE}/api/v1/catalog/departments", timeout=TIMEOUT))
    assert check(public.get(f"{BASE}/api/v1/catalog/categories", timeout=TIMEOUT))
    assert check(public.get(f"{BASE}/api/v1/cms/public/pages/about", timeout=TIMEOUT))["content_type"] == "page"
    assert check(public.get(f"{BASE}/api/v1/cms/public/faq", timeout=TIMEOUT))["items"]

    _, failed_order, failed_payment = guest_order("FAILED")
    assert failed_payment["payment_status"] == "failed"
    assert failed_payment["order_payment_state"] == "failed"
    assert failed_order["access_token"]

    _, paid_order, paid_payment = guest_order("SUCCESS")
    assert paid_payment["payment_status"] == "paid"
    assert paid_payment["order_payment_state"] == "paid"

    admin = requests.Session()
    login = post(admin, "/api/v1/auth/login", {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert login["role"] == "admin"
    csrf = admin.cookies.get("csrf_token")
    assert csrf
    admin.headers.update({"X-CSRF-Token": csrf})
    assert check(admin.get(f"{BASE}/api/v1/admin/dashboard", timeout=TIMEOUT))["total_products"] > 0
    detail = check(admin.get(f"{BASE}/api/v1/admin/orders/{paid_order['order_number']}", timeout=TIMEOUT))
    assert detail["payment"]["id"]
    refunded = post(admin, f"/api/v1/admin/payments/{detail['payment']['id']}/refund", {})
    assert refunded["status"] == "refunded"
    tracked_refund = check(
        public.get(
            f"{BASE}/api/v1/orders/track",
            params={"order_number": paid_order["order_number"], "token": paid_order["access_token"]},
            timeout=TIMEOUT,
        )
    )
    assert tracked_refund["payment_state"] == "refunded"
    audit = check(admin.get(f"{BASE}/api/v1/admin/audit", timeout=TIMEOUT))
    assert any(row.get("action") == "admin.payment.refund" for row in audit["items"])

    print("LOCAL SMOKE PASS: readiness, public catalog/CMS, seller boundary, guest failure/success, admin refund/audit")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, requests.RequestException) as exc:
        print(f"LOCAL SMOKE FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
