"""Security and contract coverage for the manual order lifecycle."""

import os

import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
API = f"{BASE}/api/v1"
CUSTOMER = ("customer.demo@muslimahcantik.id", "MC-Cust0mer-9d2m48Lw-2026")
ADMIN = ("bmulyanto@gmail.com", "MC-Adm1n-7f3k29xQ-2026")


def _login(credentials):
    session = requests.Session()
    response = session.post(
        f"{API}/auth/login",
        json={"email": credentials[0], "password": credentials[1]},
    )
    assert response.status_code == 200, response.text
    session.headers["X-CSRF-Token"] = session.cookies.get("csrf_token")
    return session


def test_manual_order_admin_surface_is_protected():
    assert requests.get(f"{API}/admin/telegram-inquiries").status_code == 401
    assert requests.get(f"{API}/admin/payment-destinations").status_code == 401
    assert requests.post(f"{API}/admin/payment-destinations", json={}).status_code == 401
    assert (
        requests.post(f"{API}/admin/orders/MC-NOT-REAL/payment/confirm").status_code
        == 401
    )


def test_customer_cannot_read_or_mutate_manual_order_surface():
    customer = _login(CUSTOMER)
    assert customer.get(f"{API}/admin/telegram-inquiries").status_code == 403
    assert customer.get(f"{API}/admin/payment-destinations").status_code == 403
    assert customer.post(f"{API}/admin/payment-destinations", json={}).status_code == 403
    assert (
        customer.post(f"{API}/admin/orders/MC-NOT-REAL/payment/confirm").status_code
        == 403
    )


def test_admin_workflow_merges_orders_and_filters_empty_inquiries():
    admin = _login(ADMIN)
    response = admin.get(
        f"{API}/admin/order-workflow",
        params={"scope": "all", "page_size": 100},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert set(payload["counts"]) >= {"inquiry", "payment_review", "delivered"}
    assert all(
        item.get("item_count", 0) > 0
        for item in payload["items"]
        if item["kind"] == "inquiry"
    )


def test_guest_timeline_requires_opaque_order_access():
    response = requests.get(
        f"{API}/orders/track",
        params={"order_number": "MC-NOT-REAL", "token": "invalid-token"},
    )
    assert response.status_code == 404
