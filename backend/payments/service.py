"""Payment domain service — single place where payment/order state changes.

All irreversible transitions run inside the caller's session transaction
with a row-level lock (SELECT ... FOR UPDATE) on the payment row.
Prepare/Complete validation order per CLICK reference:
required fields -> action -> service_id -> signature (raw strings) ->
merchant_trans_id lookup -> amount -> state.
"""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Order, Payment, PaymentEvent
from payments import errors
from payments.errors import ClickProtocolError
from payments.signature import verify_signature

REQUIRED_PREPARE = [
    "click_trans_id", "service_id", "click_paydoc_id", "merchant_trans_id",
    "amount", "action", "error", "error_note", "sign_time", "sign_string",
]
REQUIRED_COMPLETE = REQUIRED_PREPARE + ["merchant_prepare_id"]

PAYMENT_STATUSES = (
    "pending", "prepared", "paid", "failed", "cancelled",
    "expired", "reversed", "refunded",
)


def _require_fields(raw: dict, fields: list) -> None:
    if any(f not in raw or raw[f] is None for f in fields):
        raise ClickProtocolError(errors.INVALID_REQUEST, "Missing required fields")


def _parse_amount(raw_amount: str) -> Decimal:
    # Signature has already been verified against the RAW string at this
    # point; only now is the semantic value parsed.
    try:
        return Decimal(raw_amount)
    except InvalidOperation:
        raise ClickProtocolError(errors.INVALID_REQUEST, "Unparseable amount")


def _echo_id(value):
    text = str(value) if value is not None else None
    return int(text) if text and text.isdigit() else value


class PaymentService:
    def __init__(self, session: AsyncSession, provider):
        self.session = session
        self.provider = provider

    async def _log_event(
        self,
        payment: Optional[Payment],
        event_type: str,
        result: str,
        click_trans_id: Optional[str] = None,
        provider_error_code: Optional[str] = None,
        meta: Optional[dict] = None,
    ) -> None:
        # Audit records must never contain secrets — only safe metadata.
        self.session.add(
            PaymentEvent(
                payment_id=payment.id if payment else None,
                provider=self.provider.name,
                environment=self.provider.environment,
                event_type=event_type,
                click_trans_id=click_trans_id,
                provider_error_code=provider_error_code,
                meta=meta or {},
                result=result,
            )
        )

    async def create_payment(
        self,
        order: Order,
        idempotency_key: Optional[str] = None,
    ) -> Payment:
        key = idempotency_key or f"order-{order.id}"
        existing = await self.session.scalar(
            select(Payment).where(Payment.idempotency_key == key)
        )
        if existing:
            return existing
        payment = Payment(
            order_id=order.id,
            provider=self.provider.name,
            environment=self.provider.environment,
            currency=order.currency,
            amount=order.grand_total,
            status="pending",
            merchant_trans_id=str(order.id),
            idempotency_key=key,
        )
        self.session.add(payment)
        await self.session.flush()
        await self._log_event(payment, "CREATE", "ok")
        return payment

    async def _locked_payment(self, merchant_trans_id: str) -> Payment:
        payment = await self.session.scalar(
            select(Payment)
            .where(
                Payment.merchant_trans_id == merchant_trans_id,
                Payment.provider == self.provider.name,
            )
            .with_for_update()
        )
        if not payment:
            raise ClickProtocolError(errors.ORDER_NOT_FOUND, "Unknown merchant_trans_id")
        return payment

    def _validate_common(self, raw: dict, required: list, action: str) -> None:
        _require_fields(raw, required)
        if raw["action"] != action:
            raise ClickProtocolError(errors.INVALID_ACTION, "Wrong action")
        if raw["service_id"] != self.provider.get_service_id():
            raise ClickProtocolError(errors.INVALID_REQUEST, "Unknown service_id")
        if not verify_signature(raw, self.provider.get_signing_secret(), action):
            raise ClickProtocolError(errors.SIGNATURE_FAILED, "Signature check failed")

    def _validate_amount(self, raw: dict, payment: Payment) -> None:
        if _parse_amount(raw["amount"]) != Decimal(payment.amount):
            raise ClickProtocolError(errors.INCORRECT_AMOUNT, "Amount mismatch")

    async def prepare(self, raw: dict) -> dict:
        self._validate_common(raw, REQUIRED_PREPARE, "0")
        payment = await self._locked_payment(raw["merchant_trans_id"])
        self._validate_amount(raw, payment)

        if payment.status == "prepared":
            # Idempotent replay of the same Prepare
            return self._prepare_response(raw, payment, errors.SUCCESS, "Success")
        if payment.status in ("paid", "cancelled", "refunded"):
            code = errors.ALREADY_PAID if payment.status == "paid" else errors.UPDATE_FAILURE
            await self._log_event(
                payment, "PREPARE", "rejected",
                click_trans_id=raw["click_trans_id"], provider_error_code=str(code),
                meta={"reason": f"status_{payment.status}"},
            )
            raise ClickProtocolError(code, f"Cannot prepare in status {payment.status}")

        payment.status = "prepared"
        payment.merchant_prepare_id = payment.id
        payment.click_trans_id = raw["click_trans_id"]
        payment.click_paydoc_id = raw["click_paydoc_id"]
        await self._log_event(
            payment, "PREPARE", "ok", click_trans_id=raw["click_trans_id"]
        )
        await self.session.commit()
        return self._prepare_response(raw, payment, errors.SUCCESS, "Success")

    def _prepare_response(self, raw, payment, code, note) -> dict:
        return {
            "click_trans_id": _echo_id(raw["click_trans_id"]),
            "merchant_trans_id": raw["merchant_trans_id"],
            "merchant_prepare_id": _echo_id(payment.merchant_prepare_id),
            "error": code,
            "error_note": note,
        }

    async def complete(self, raw: dict) -> dict:
        self._validate_common(raw, REQUIRED_COMPLETE, "1")
        payment = await self._locked_payment(raw["merchant_trans_id"])
        self._validate_amount(raw, payment)

        if payment.status == "paid":
            if payment.click_trans_id == raw["click_trans_id"]:
                # True idempotent replay of the same successful Complete
                return self._complete_response(raw, payment, errors.SUCCESS, "Success")
            await self._log_event(
                payment, "COMPLETE", "rejected",
                click_trans_id=raw["click_trans_id"],
                provider_error_code=str(errors.ALREADY_PAID),
            )
            raise ClickProtocolError(errors.ALREADY_PAID, "Already paid")
        if payment.status != "prepared" or (
            payment.merchant_prepare_id != raw["merchant_prepare_id"]
        ):
            raise ClickProtocolError(
                errors.TRANSACTION_NOT_FOUND, "Prepared transaction not found"
            )

        # CLICK-reported payment failure/cancellation (error < 0 in callback)
        if raw.get("error", "0") != "0":
            cancelled = raw["error"] == str(errors.TRANSACTION_CANCELLED)
            payment.status = "cancelled" if cancelled else "failed"
            payment.failure_code = raw["error"]
            payment.failure_note = raw.get("error_note", "")[:255]
            if cancelled:
                payment.cancelled_at = datetime.now(timezone.utc)
            await self._log_event(
                payment, "COMPLETE", "failed",
                click_trans_id=raw["click_trans_id"],
                provider_error_code=raw["error"],
                meta={"note": raw.get("error_note", "")[:120]},
            )
            await self.session.commit()
            return self._complete_response(raw, payment, errors.SUCCESS, "Success")

        payment.status = "paid"
        payment.paid_at = datetime.now(timezone.utc)
        payment.merchant_confirm_id = payment.id
        await self._on_payment_paid(payment)
        await self._log_event(
            payment, "COMPLETE", "ok", click_trans_id=raw["click_trans_id"]
        )
        await self.session.commit()
        return self._complete_response(raw, payment, errors.SUCCESS, "Success")

    def _complete_response(self, raw, payment, code, note) -> dict:
        return {
            "click_trans_id": _echo_id(raw["click_trans_id"]),
            "merchant_trans_id": raw["merchant_trans_id"],
            "merchant_confirm_id": _echo_id(payment.merchant_confirm_id),
            "error": code,
            "error_note": note,
        }

    async def _on_payment_paid(self, payment: Payment) -> None:
        """Exactly-once payment -> order transition boundary.

        Future Checkout effects (inventory commit, cart clearing) attach
        here — behind this single service method, never in callbacks.
        """
        order = await self.session.get(Order, payment.order_id)
        if order and order.payment_state != "paid":
            order.payment_state = "paid"
            order.status = "paid"

    async def expire(self, payment: Payment) -> Payment:
        locked = await self._locked_payment(payment.merchant_trans_id)
        if locked.status in ("pending", "prepared"):
            locked.status = "expired"
            await self._log_event(locked, "EXPIRE", "ok")
            await self.session.commit()
        return locked

    async def refund(self, merchant_trans_id: str, note: str = "") -> Payment:
        payment = await self._locked_payment(merchant_trans_id)
        if payment.status != "paid":
            raise ClickProtocolError(
                errors.UPDATE_FAILURE, f"Cannot refund in status {payment.status}"
            )
        payment.status = "refunded"
        payment.cancelled_at = datetime.now(timezone.utc)
        order = await self.session.get(Order, payment.order_id)
        if order and order.status not in ("refunded",):
            order.status = "refunded"
        await self._log_event(
            payment, "REFUND", "ok", meta={"note": note[:120]} if note else {}
        )
        await self.session.commit()
        return payment

    async def get_status(self, merchant_trans_id: str) -> dict:
        payment = await self.session.scalar(
            select(Payment).where(
                Payment.merchant_trans_id == merchant_trans_id,
                Payment.provider == self.provider.name,
            )
        )
        if not payment:
            raise ClickProtocolError(errors.ORDER_NOT_FOUND, "Unknown merchant_trans_id")
        return {
            "merchant_trans_id": payment.merchant_trans_id,
            "status": payment.status,
            "amount": payment.amount,
            "currency": payment.currency,
            "paid_at": payment.paid_at,
        }
