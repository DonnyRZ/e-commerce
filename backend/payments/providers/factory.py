"""Provider factory — mode gates. No silent fallbacks, ever."""

from payments.providers.base import PaymentProvider
from payments.providers.click import ClickProvider
from payments.providers.mock_click import MockClickProvider


def get_provider() -> PaymentProvider:
    from config import (
        CLICK_MERCHANT_ID,
        CLICK_MERCHANT_USER_ID,
        CLICK_API_BASE_URL,
        CLICK_MODE,
        CLICK_MOCK_SECRET_KEY,
        CLICK_PAYMENT_URL,
        CLICK_SECRET_KEY,
        CLICK_SERVICE_ID,
        PAYMENT_PROVIDER,
    )

    if PAYMENT_PROVIDER != "click":
        raise RuntimeError(f"Unsupported PAYMENT_PROVIDER: {PAYMENT_PROVIDER}")

    if CLICK_MODE == "mock":
        if not CLICK_MOCK_SECRET_KEY:
            raise RuntimeError("CLICK_MODE=mock requires CLICK_MOCK_SECRET_KEY")
        return MockClickProvider(secret_key=CLICK_MOCK_SECRET_KEY)

    if CLICK_MODE in ("test", "production"):
        missing = [
            name
            for name, value in {
                "CLICK_SERVICE_ID": CLICK_SERVICE_ID,
                "CLICK_MERCHANT_ID": CLICK_MERCHANT_ID,
                "CLICK_MERCHANT_USER_ID": CLICK_MERCHANT_USER_ID,
                "CLICK_SECRET_KEY": CLICK_SECRET_KEY,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(
                f"CLICK_MODE={CLICK_MODE} requires configuration: {', '.join(missing)}"
            )
        return ClickProvider(
            mode=CLICK_MODE,
            service_id=CLICK_SERVICE_ID,
            merchant_id=CLICK_MERCHANT_ID,
            secret_key=CLICK_SECRET_KEY,
            payment_url=CLICK_PAYMENT_URL,
            api_base_url=CLICK_API_BASE_URL,
            merchant_user_id=CLICK_MERCHANT_USER_ID,
        )

    # Unknown mode: fail closed, never fall back to production.
    raise RuntimeError(f"Unknown CLICK_MODE: {CLICK_MODE}")
