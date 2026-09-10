"""Shipping provider factory — mode gates, no silent fallbacks."""

from shipping.base import ShippingProvider
from shipping.mock import MockShippingProvider


def get_shipping_provider() -> ShippingProvider:
    from config import SHIPPING_PROVIDER

    if SHIPPING_PROVIDER == "mock":
        return MockShippingProvider()
    raise RuntimeError(f"Unsupported SHIPPING_PROVIDER: {SHIPPING_PROVIDER}")
