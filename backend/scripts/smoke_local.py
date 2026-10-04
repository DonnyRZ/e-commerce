"""Repeatable local storefront/Admin smoke test.

Run against an isolated database and a running API server. The current local
release intentionally keeps checkout disabled until a payment workflow is
selected and implemented.
"""

from __future__ import annotations

import os
import sys

import requests


BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000").rstrip("/")
ADMIN_EMAIL = os.environ.get("SMOKE_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("SMOKE_ADMIN_PASSWORD", "")
TIMEOUT = 10


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check(response: requests.Response, expected: int = 200) -> dict:
    if response.status_code != expected:
        raise AssertionError(
            f"{response.request.method} {response.request.url} -> "
            f"{response.status_code}, expected {expected}: {response.text[:500]}"
        )
    if not response.content:
        return {}
    return response.json()


def main() -> int:
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        raise SystemExit("SMOKE_ADMIN_EMAIL and SMOKE_ADMIN_PASSWORD are required")

    public = requests.Session()
    ready = check(public.get(f"{BASE}/api/ready", timeout=TIMEOUT))
    require(
        ready["checks"]["payment"] == "disabled",
        f"payment readiness must be disabled: {ready}",
    )
    require(
        ready["checkout_enabled"] is False,
        f"checkout must be disabled: {ready}",
    )
    require(
        all(
            value == "up" or (name == "payment" and value == "disabled")
            for name, value in ready["checks"].items()
        ),
        f"all required readiness checks must be up: {ready}",
    )
    schema = check(public.get(f"{BASE}/openapi.json", timeout=TIMEOUT))
    require(
        not any(path.startswith("/api/v1/payments/") for path in schema.get("paths", {})),
        "payment API routes must not be exposed while checkout is disabled",
    )
    require(
        not any(path.endswith("/refund") for path in schema.get("paths", {})),
        "refund API route must not be exposed while checkout is disabled",
    )
    check(public.get(f"{BASE}/api/status", timeout=TIMEOUT), 404)
    check(public.get(f"{BASE}/api/v1/seller/dashboard", timeout=TIMEOUT), 404)
    require(
        bool(check(public.get(f"{BASE}/api/v1/catalog/departments", timeout=TIMEOUT))),
        "catalog departments must be seeded",
    )
    require(
        bool(check(public.get(f"{BASE}/api/v1/catalog/categories", timeout=TIMEOUT))),
        "catalog categories must be seeded",
    )
    about = check(public.get(f"{BASE}/api/v1/cms/public/pages/about", timeout=TIMEOUT))
    require(
        about.get("content_type") == "page",
        f"about CMS page must be available: {about}",
    )
    faq = check(public.get(f"{BASE}/api/v1/cms/public/faq", timeout=TIMEOUT))
    require(bool(faq.get("items")), f"CMS FAQ defaults must be seeded: {faq}")

    products = check(
        public.get(
            f"{BASE}/api/v1/catalog/products",
            params={"limit": 1, "availability": "in_stock"},
            timeout=TIMEOUT,
        )
    )
    product = products["items"][0]
    detail = check(public.get(f"{BASE}/api/v1/catalog/products/{product['slug']}", timeout=TIMEOUT))
    # Pre-order availability is based on active catalog state, not stock.
    variant = next(v for v in detail["variants"] if v["is_active"])
    cart = check(
        public.post(
            f"{BASE}/api/v1/cart/items",
            json={"product_id": product["id"], "variant_id": variant["id"], "quantity": 1},
            timeout=TIMEOUT,
        ),
        201,
    )
    require(cart["item_count"] == 1, f"cart should contain one item after add: {cart}")
    options = check(public.get(f"{BASE}/api/v1/checkout/options", timeout=TIMEOUT))
    require(options["checkout_enabled"] is False, f"checkout must be disabled: {options}")
    require(
        options["payment_methods"] == [],
        f"payment methods must be empty: {options}",
    )
    require(
        options["payment_mode"] == "disabled",
        f"payment mode must be disabled: {options}",
    )
    check(
        public.post(
            f"{BASE}/api/v1/checkout/quote",
            json={"shipping_method": "standard"},
            timeout=TIMEOUT,
        ),
        503,
    )
    check(
        public.post(
            f"{BASE}/api/v1/checkout/orders",
            json={"idempotency_key": "smoke-disabled-123", "shipping_method": "standard"},
            timeout=TIMEOUT,
        ),
        503,
    )
    check(public.delete(f"{BASE}/api/v1/cart", timeout=TIMEOUT), 204)

    admin = requests.Session()
    login = check(
        admin.post(
            f"{BASE}/api/v1/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=TIMEOUT,
        )
    )
    require(
        login.get("role") == "admin",
        f"smoke account must authenticate as admin: {login}",
    )
    csrf = admin.cookies.get("csrf_token")
    require(bool(csrf), "admin login should issue the CSRF cookie")
    admin.headers.update({"X-CSRF-Token": csrf})
    settings = check(admin.get(f"{BASE}/api/v1/admin/settings", timeout=TIMEOUT))
    require(
        settings.get("payment_status") == "disabled",
        f"payment status must be disabled: {settings}",
    )
    dashboard = check(admin.get(f"{BASE}/api/v1/admin/dashboard", timeout=TIMEOUT))
    require(
        dashboard.get("total_products", 0) > 0,
        f"admin dashboard should include seeded products: {dashboard}",
    )

    print("LOCAL SMOKE PASS: readiness, public catalog/CMS, cart, disabled checkout, admin")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, requests.RequestException) as exc:
        print(f"LOCAL SMOKE FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
