"""CLICK Shop API routes + mock simulator.

- Prepare/Complete accept raw form-encoded callbacks; raw strings are
  passed UNTOUCHED to signature validation (CLICK reference §26).
- Mock simulator exists only when CLICK_MODE=mock; otherwise 404.
"""

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import BASE_CURRENCY, CLICK_MODE
from db.models import Order, Payment, PaymentEvent
from db.session import get_session
from payments.errors import ClickProtocolError
from payments.providers import get_provider
from payments.providers.mock_click import ALL_SCENARIOS
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
from payments.service import PaymentService

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


def _protocol_response(raw: dict, payload: dict = None, error: int = 0, note: str = "Success") -> JSONResponse:
    body = payload or {
        "click_trans_id": int(raw["click_trans_id"]) if str(raw.get("click_trans_id", "")).isdigit() else raw.get("click_trans_id"),
        "merchant_trans_id": raw.get("merchant_trans_id"),
        "error": error,
        "error_note": note,
    }
    return JSONResponse(body)


@router.post("/click/prepare")
async def click_prepare(request: Request, session: AsyncSession = Depends(get_session)):
    form = await request.form()
    raw = {k: str(v) for k, v in form.items()}  # raw strings preserved
    provider = get_provider()
    service = PaymentService(session, provider)
    try:
        result = await service.prepare(raw)
    except ClickProtocolError as exc:
        await session.rollback()
        return _protocol_response(raw, error=exc.code, note=exc.note)
    return _protocol_response(raw, payload=result)


@router.post("/click/complete")
async def click_complete(request: Request, session: AsyncSession = Depends(get_session)):
    form = await request.form()
    raw = {k: str(v) for k, v in form.items()}
    provider = get_provider()
    service = PaymentService(session, provider)
    try:
        result = await service.complete(raw)
    except ClickProtocolError as exc:
        await session.rollback()
        return _protocol_response(raw, error=exc.code, note=exc.note)
    return _protocol_response(raw, payload=result)


# ---------------------------------------------------------------------------
# Mock simulator — development/test only. Hard-gated by CLICK_MODE=mock.
# ---------------------------------------------------------------------------


def _require_mock_mode() -> None:
    from fastapi import HTTPException

    if CLICK_MODE != "mock":
        raise HTTPException(status_code=404, detail="Not found")


class MockOrderIn(BaseModel):
    amount: int = Field(gt=0, le=10**12)


class MockSimulateIn(BaseModel):
    merchant_trans_id: str
    scenario: str


@router.post("/mock/order", status_code=201)
async def mock_create_order(
    payload: MockOrderIn,
    session: AsyncSession = Depends(get_session),
):
    _require_mock_mode()
    provider = get_provider()
    service = PaymentService(session, provider)
    order = Order(
        order_number=f"SIM-{uuid.uuid4().hex[:10].upper()}",
        guest_email="simulator@mock.local",
        subtotal=payload.amount,
        grand_total=payload.amount,
        currency=BASE_CURRENCY,
        status="pending_payment",
        payment_state="unpaid",
        idempotency_key=f"sim-{uuid.uuid4().hex[:12]}",
    )
    session.add(order)
    await session.flush()
    payment = await service.create_payment(order)
    await session.commit()
    return {
        "order_id": order.id,
        "order_number": order.order_number,
        "payment_id": payment.id,
        "merchant_trans_id": payment.merchant_trans_id,
        "amount": payment.amount,
        "currency": payment.currency,
        "status": payment.status,
    }


@router.get("/mock/status/{merchant_trans_id}")
async def mock_status(merchant_trans_id: str, session: AsyncSession = Depends(get_session)):
    _require_mock_mode()
    service = PaymentService(session, get_provider())
    try:
        status = await service.get_status(merchant_trans_id)
    except ClickProtocolError as exc:
        return JSONResponse({"error": exc.code, "error_note": exc.note}, status_code=404)
    events = (
        await session.execute(
            select(PaymentEvent)
            .join(Payment, PaymentEvent.payment_id == Payment.id)
            .where(Payment.merchant_trans_id == merchant_trans_id)
            .order_by(PaymentEvent.created_at)
        )
    ).scalars().all()
    status["events"] = [
        {"event_type": e.event_type, "result": e.result, "provider_error_code": e.provider_error_code}
        for e in events
    ]
    return status


@router.post("/mock/simulate")
async def mock_simulate(
    payload: MockSimulateIn, session: AsyncSession = Depends(get_session)
):
    _require_mock_mode()
    if payload.scenario not in ALL_SCENARIOS:
        return JSONResponse({"error": "unknown_scenario", "scenarios": ALL_SCENARIOS}, status_code=422)
    provider = get_provider()
    service = PaymentService(session, provider)
    payment = await session.scalar(
        select(Payment).where(Payment.merchant_trans_id == payload.merchant_trans_id)
    )
    if not payment:
        return JSONResponse({"error": "payment_not_found"}, status_code=404)

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

    scenario = payload.scenario
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
