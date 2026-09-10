"""MockClickProvider — deterministic in-process CLICK simulation.

ZERO external network requests, ZERO real money. Simulated callbacks are
built as raw form strings, signed with CLICK_MOCK_SECRET_KEY, and passed
through the very same service handlers used by the real callback routes.
"""

from datetime import datetime, timezone
from typing import Optional

from payments.providers.base import PaymentProvider
from payments.signature import compute_signature

# scenario names
SUCCESS = "SUCCESS"
FAILED = "FAILED"
CANCELLED = "CANCELLED"
EXPIRED = "EXPIRED"
TIMEOUT = "TIMEOUT"
WRONG_AMOUNT = "WRONG_AMOUNT"
INVALID_SIGNATURE = "INVALID_SIGNATURE"
ORDER_NOT_FOUND = "ORDER_NOT_FOUND"
TRANSACTION_NOT_FOUND = "TRANSACTION_NOT_FOUND"
DUPLICATE_PREPARE = "DUPLICATE_PREPARE"
DUPLICATE_COMPLETE = "DUPLICATE_COMPLETE"
ALREADY_PAID = "ALREADY_PAID"
REFUND = "REFUND"

ALL_SCENARIOS = [
    SUCCESS, FAILED, CANCELLED, EXPIRED, TIMEOUT, WRONG_AMOUNT,
    INVALID_SIGNATURE, ORDER_NOT_FOUND, TRANSACTION_NOT_FOUND,
    DUPLICATE_PREPARE, DUPLICATE_COMPLETE, ALREADY_PAID, REFUND,
]


class MockClickProvider(PaymentProvider):
    name = "click"
    environment = "mock"

    def __init__(self, secret_key: str, service_id: str = "mock-service"):
        self._secret = secret_key
        self._service_id = service_id

    def get_service_id(self) -> str:
        return self._service_id

    def get_signing_secret(self) -> str:
        return self._secret

    def build_payment_url(
        self, merchant_trans_id: str, amount: int, return_url: str = ""
    ) -> str:
        # mock has no hosted page; this URL is a development stand-in only
        return f"mock://click/pay?merchant_trans_id={merchant_trans_id}&amount={amount}"

    def build_prepare_params(
        self,
        payment,
        click_trans_id: str,
        amount_override: Optional[str] = None,
        tamper_signature: bool = False,
    ) -> dict:
        fields = {
            "click_trans_id": click_trans_id,
            "service_id": self._service_id,
            "click_paydoc_id": f"PDOC-{click_trans_id}",
            "merchant_trans_id": payment.merchant_trans_id,
            "amount": amount_override if amount_override is not None else str(payment.amount),
            "action": "0",
            "error": "0",
            "error_note": "",
            "sign_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        }
        fields["sign_string"] = compute_signature(fields, self._secret, "0")
        if tamper_signature:
            fields["sign_string"] = "0" * 32
        return fields

    def build_complete_params(
        self,
        payment,
        click_trans_id: str,
        amount_override: Optional[str] = None,
        tamper_signature: bool = False,
        prepare_id_override: Optional[str] = None,
        error: str = "0",
        error_note: str = "",
    ) -> dict:
        fields = {
            "click_trans_id": click_trans_id,
            "service_id": self._service_id,
            "click_paydoc_id": f"PDOC-{click_trans_id}",
            "merchant_trans_id": payment.merchant_trans_id,
            "merchant_prepare_id": prepare_id_override
            if prepare_id_override is not None
            else (payment.merchant_prepare_id or ""),
            "amount": amount_override if amount_override is not None else str(payment.amount),
            "action": "1",
            "error": error,
            "error_note": error_note,
            "sign_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        }
        fields["sign_string"] = compute_signature(fields, self._secret, "1")
        if tamper_signature:
            fields["sign_string"] = "0" * 32
        return fields
