"""The deployable API exposes a single-operator Admin Console only."""

import os

import requests


BASE = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
API = f"{BASE}/api/v1"


def test_legacy_seller_surface_is_not_public():
    for path in ("/seller/dashboard", "/seller/products", "/seller/orders"):
        response = requests.get(f"{API}{path}", timeout=10)
        assert response.status_code == 404, (path, response.status_code, response.text)
