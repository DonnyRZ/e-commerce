from abc import ABC, abstractmethod


class ShippingProvider(ABC):
    """Shipping boundary — checkout totals never depend on a concrete courier."""

    name: str = "abstract"

    @abstractmethod
    def list_methods(self, merchandise_subtotal: int = 0) -> list[dict]:
        ...

    @abstractmethod
    def quote(self, method_code: str, merchandise_subtotal: int) -> dict:
        ...
