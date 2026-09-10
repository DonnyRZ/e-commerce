from abc import ABC, abstractmethod
from typing import Mapping


class PaymentProvider(ABC):
    """Provider boundary — business logic never depends on a concrete adapter."""

    name: str = "abstract"
    environment: str = "mock"

    @abstractmethod
    def get_service_id(self) -> str:
        ...

    @abstractmethod
    def get_signing_secret(self) -> str:
        ...

    @abstractmethod
    def build_payment_url(
        self, merchant_trans_id: str, amount: int, return_url: str = ""
    ) -> str:
        ...
