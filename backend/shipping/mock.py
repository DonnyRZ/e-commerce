"""MockShippingProvider — deterministic server-defined UZS rates.

Zero external network. Replaceable by a real courier adapter later.
Frontend-supplied shipping costs are never accepted; rates are defined here.
"""

from config import BASE_CURRENCY
from shipping.base import ShippingProvider

# Matches the storefront promise: free standard shipping over UZS 550,000.
FREE_STANDARD_THRESHOLD = 550_000

_METHODS = (
    {"code": "standard", "label": "Standard", "amount": 30_000, "eta": "3-5"},
    {"code": "express", "label": "Express", "amount": 65_000, "eta": "1-2"},
)


class UnknownShippingMethod(KeyError):
    pass


class MockShippingProvider(ShippingProvider):
    name = "mock"

    def quote(self, method_code: str, merchandise_subtotal: int) -> dict:
        method = next((m for m in _METHODS if m["code"] == method_code), None)
        if not method:
            raise UnknownShippingMethod(method_code)
        amount = method["amount"]
        if method_code == "standard" and merchandise_subtotal >= FREE_STANDARD_THRESHOLD:
            amount = 0
        return {
            "code": method["code"],
            "label": method["label"],
            "amount": amount,
            "currency": BASE_CURRENCY,
            "eta": method["eta"],
        }

    def list_methods(self, merchandise_subtotal: int = 0) -> list[dict]:
        return [self.quote(m["code"], merchandise_subtotal) for m in _METHODS]
