"""ClickProvider — real CLICK adapter (test/production).

Callback handling (Prepare/Complete) is INBOUND: CLICK calls our server,
so no outbound network happens here. Outbound Merchant API calls are
explicitly deferred until real merchant credentials exist.
"""

from payments.providers.base import PaymentProvider


class ClickProvider(PaymentProvider):
    name = "click"

    def __init__(self, *, mode: str, service_id: str, secret_key: str, payment_url: str):
        self.environment = mode  # test | production
        self._service_id = service_id
        self._secret = secret_key
        self._payment_url = payment_url

    def get_service_id(self) -> str:
        return self._service_id

    def get_signing_secret(self) -> str:
        return self._secret

    def build_payment_url(
        self, merchant_trans_id: str, amount: int, return_url: str = ""
    ) -> str:
        if not self._payment_url:
            raise RuntimeError("CLICK_PAYMENT_URL is not configured")
        url = f"{self._payment_url}?service_id={self._service_id}&merchant_id=&transaction_param={merchant_trans_id}&amount={amount}"
        if return_url:
            url += f"&return_url={return_url}"
        return url
