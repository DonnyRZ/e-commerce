"""Checkout contract while no payment method is configured."""

import os

import requests


BASE = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
API = f"{BASE}/api/v1"


def _preorder_product():
    response = requests.get(
        f"{API}/catalog/products",
        params={"limit": 60},
        timeout=10,
    )
    assert response.status_code == 200, response.text
    product = next(
        item for item in response.json()["items"]
    )
    detail = requests.get(f"{API}/catalog/products/{product['slug']}", timeout=10)
    assert detail.status_code == 200, detail.text
    variant = next(
        item for item in detail.json()["variants"]
        if item["is_active"]
    )
    return product, variant


def test_checkout_options_are_disabled_without_payment_method():
    response = requests.get(f"{API}/checkout/options", timeout=10)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["checkout_enabled"] is False
    assert payload["payment_methods"] == []
    assert payload["payment_mode"] == "disabled"


def test_checkout_mutations_fail_closed():
    quote = requests.post(
        f"{API}/checkout/quote",
        json={"shipping_method": "standard"},
        timeout=10,
    )
    assert quote.status_code == 503, quote.text
    assert quote.json()["detail"]["error"] == "checkout_unavailable"

    order = requests.post(
        f"{API}/checkout/orders",
        json={
            "idempotency_key": "disabled-checkout-test-1",
            "shipping_method": "standard",
            "email": "test@example.com",
            "address": {
                "recipient_name": "Test User",
                "phone": "+998901112233",
                "address_line_1": "1 Test Street",
                "city": "Tashkent",
                "state_province": "Tashkent",
                "postal_code": "100000",
                "country_code": "UZ",
            },
        },
        timeout=10,
    )
    assert order.status_code == 503, order.text
    assert order.json()["detail"]["error"] == "checkout_unavailable"


def test_cart_remains_available_while_checkout_is_disabled():
    product, variant = _preorder_product()
    session = requests.Session()
    added = session.post(
        f"{API}/cart/items",
        json={
            "product_id": product["id"],
            "variant_id": variant["id"],
            "quantity": 1,
        },
        timeout=10,
    )
    assert added.status_code == 201, added.text
    assert added.json()["item_count"] == 1
    cart = session.get(f"{API}/cart", timeout=10)
    assert cart.status_code == 200, cart.text
    assert cart.json()["item_count"] == 1
    cleared = session.delete(f"{API}/cart", timeout=10)
    assert cleared.status_code == 204, cleared.text


def test_retired_payment_routes_are_not_registered():
    response = requests.get(f"{BASE}/openapi.json", timeout=10)
    assert response.status_code == 200, response.text
    paths = response.json().get("paths", {})
    assert not any(path.startswith("/api/v1/payments/") for path in paths)
    assert not any(path.endswith("/refund") for path in paths)
