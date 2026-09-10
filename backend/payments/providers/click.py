"""CLICK hosted-payment adapter for test/production environments."""

import hashlib
import time
from urllib.parse import urlencode

import httpx

from payments.providers.base import PaymentProvider


class ClickProvider(PaymentProvider):
    name = "click"

    def __init__(
        self,
        *,
        mode: str,
        service_id: str,
        merchant_id: str,
        secret_key: str,
        payment_url: str,
        api_base_url: str,
        merchant_user_id: str,
    ):
        self.environment = mode  # test | production
        self._service_id = service_id
        self._merchant_id = merchant_id
        self._secret = secret_key
        self._payment_url = payment_url
        self._api_base_url = api_base_url.rstrip("/")
        self._merchant_user_id = merchant_user_id

    def get_service_id(self) -> str:
        return self._service_id

    def get_signing_secret(self) -> str:
        return self._secret

    def build_payment_url(
        self, merchant_trans_id: str, amount: int, return_url: str = ""
    ) -> str:
        if not self._payment_url:
            raise RuntimeError("CLICK_PAYMENT_URL is not configured")
        params = {
            "service_id": self._service_id,
            "merchant_id": self._merchant_id,
            "transaction_param": merchant_trans_id,
            "amount": str(amount),
        }
        if return_url:
            params["return_url"] = return_url
        return f"{self._payment_url}?{urlencode(params)}"

    async def refund(self, click_payment_id: str) -> dict:
        """Reverse a paid Click transaction using Merchant API.

        Click's official integration uses DELETE
        ``payment/reversal/{service_id}/{payment_id}`` and an ``Auth`` header
        of ``merchant_user_id:sha1(timestamp + secret):timestamp``.
        """

        if not click_payment_id:
            raise RuntimeError("CLICK payment id is missing; manual reconciliation required")
        timestamp = str(int(time.time()))
        digest = hashlib.sha1(
            f"{timestamp}{self._secret}".encode("utf-8")
        ).hexdigest()
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Auth": f"{self._merchant_user_id}:{digest}:{timestamp}",
        }
        url = (
            f"{self._api_base_url}/payment/reversal/"
            f"{self._service_id}/{click_payment_id}"
        )
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.delete(url, headers=headers)
            response.raise_for_status()
            payload = response.json()
        if payload.get("error_code") not in (0, "0"):
            raise RuntimeError(
                f"Click reversal rejected: {payload.get('error_code')}"
            )
        return payload
