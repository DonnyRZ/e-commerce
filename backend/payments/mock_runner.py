"""Mock CLICK scenario runner — shared by the dev simulator endpoint and the
customer-facing mock payment page. Exercises the REAL PaymentService
Prepare/Complete path (signature + amount verification included); nothing
here mutates payment state directly.
"""

import uuid

from db.models import Order, Payment
from payments.errors import ClickProtocolError
from payments.providers.mock_click import (
    ALREADY_PAID,
    CANCELLED,
    DUPLICATE_COMPLETE,
    DUPLICATE_PREPARE,
    EXPIRED,
    FAILED,
    INVALID_SIGNATURE,
    ORDER_NOT_FOUND,
    REFUND,
    SUCCESS,
    TIMEOUT,
    TRANSACTION_NOT_FOUND,
    WRONG_AMOUNT,
)


async def run_scenario(session, provider, service, payment, scenario: str) -> dict:
    trans_id = uuid.uuid4().hex[:12]
    steps = []

    async def run_prepare(**kw):
        raw = provider.build_prepare_params(payment, trans_id, **kw)
        try:
            res = await service.prepare(raw)
        except ClickProtocolError as exc:
            await session.rollback()
            res = {"error": exc.code, "error_note": exc.note}
        steps.append({"step": "prepare", **{k: res.get(k) for k in ("error", "error_note", "merchant_prepare_id")}})
        return res

    async def run_complete(**kw):
        await session.refresh(payment)
        raw = provider.build_complete_params(payment, trans_id, **kw)
        try:
            res = await service.complete(raw)
        except ClickProtocolError as exc:
            await session.rollback()
            res = {"error": exc.code, "error_note": exc.note}
        steps.append({"step": "complete", **{k: res.get(k) for k in ("error", "error_note", "merchant_confirm_id")}})
        return res

    if scenario == SUCCESS:
        await run_prepare()
        await run_complete()
    elif scenario == FAILED:
        await run_prepare()
        await run_complete(error="-8", error_note="Payment failed")
    elif scenario == CANCELLED:
        await run_prepare()
        await run_complete(error="-9", error_note="Transaction cancelled")
    elif scenario == TIMEOUT:
        await run_prepare()  # no complete arrives
    elif scenario == EXPIRED:
        await run_prepare()
        await session.refresh(payment)
        await service.expire(payment)
        steps.append({"step": "expire", "error": 0})
    elif scenario == WRONG_AMOUNT:
        await run_prepare()
        await run_complete(amount_override=str(payment.amount + 100))
    elif scenario == INVALID_SIGNATURE:
        await run_prepare(tamper_signature=True)
    elif scenario == ORDER_NOT_FOUND:
        ghost = Payment(
            order_id=payment.order_id, provider=provider.name,
            environment=provider.environment, amount=payment.amount,
            merchant_trans_id="ghost-trans", currency=payment.currency,
        )
        raw = provider.build_prepare_params(ghost, trans_id)
        try:
            await service.prepare(raw)
        except ClickProtocolError as exc:
            await session.rollback()
            steps.append({"step": "prepare", "error": exc.code, "error_note": exc.note})
    elif scenario == TRANSACTION_NOT_FOUND:
        await run_prepare()
        await run_complete(prepare_id_override="999999999")
    elif scenario == DUPLICATE_PREPARE:
        await run_prepare()
        await run_prepare()
    elif scenario in (DUPLICATE_COMPLETE, ALREADY_PAID):
        await run_prepare()
        await run_complete()
        if scenario == DUPLICATE_COMPLETE:
            await run_complete()
        else:
            await run_complete()  # same trans replay
            other = uuid.uuid4().hex[:12]
            await session.refresh(payment)
            raw = provider.build_complete_params(payment, other)
            try:
                await service.complete(raw)
            except ClickProtocolError as exc:
                await session.rollback()
                steps.append({"step": "complete_other_trans", "error": exc.code, "error_note": exc.note})
    elif scenario == REFUND:
        await run_prepare()
        await run_complete()
        await service.refund(payment.merchant_trans_id, note="mock refund")
        steps.append({"step": "refund", "error": 0})

    await session.refresh(payment)
    order = await session.get(Order, payment.order_id)
    return {
        "scenario": scenario,
        "steps": steps,
        "payment_status": payment.status,
        "order_status": order.status if order else None,
        "order_payment_state": order.payment_state if order else None,
    }
