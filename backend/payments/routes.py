"""CLICK Shop API routes + mock simulator.

- Prepare/Complete accept raw form-encoded callbacks; raw strings are
  passed UNTOUCHED to signature validation (CLICK reference §26).
- Mock simulator (/mock/*) exists only when CLICK_MODE=mock; otherwise 404.
- /mock/pay is the customer-facing mock payment action endpoint: it runs
  scenarios through the real Prepare/Complete service path and is
  ownership/token-authorized per order.
"""

import hmac
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import csrf_protect
from config import BASE_CURRENCY, CLICK_MODE
from db.models import Order, Payment, PaymentEvent
from db.session import get_session
from payments.errors import ClickProtocolError
from payments.mock_runner import run_scenario
from payments.providers import get_provider
from payments.providers.mock_click import ALL_SCENARIOS
from payments.providers.mock_click import (
    CANCELLED,
    EXPIRED,
    FAILED,
    SUCCESS,
    TIMEOUT,
)
from payments.service import PaymentService
from routers.shop import _optional_user

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
    return await run_scenario(session, provider, service, payment, payload.scenario)


# ---------------------------------------------------------------------------
# Customer-facing mock payment actions (dev only). Runs the real
# Prepare/Complete service flow; access is scoped to the order owner:
# auth user must own the order, guests must present the opaque access token.
# ---------------------------------------------------------------------------

CUSTOMER_SCENARIOS = [SUCCESS, FAILED, CANCELLED, TIMEOUT, EXPIRED]


class MockPayIn(BaseModel):
    merchant_trans_id: str = Field(min_length=4, max_length=80)
    order_number: str = Field(min_length=4, max_length=40)
    scenario: str
    access_token: Optional[str] = Field(default=None, max_length=80)


@router.post("/mock/pay")
async def mock_pay(
    payload: MockPayIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    _require_mock_mode()
    if payload.scenario not in CUSTOMER_SCENARIOS:
        raise HTTPException(status_code=422, detail="unknown_scenario")
    payment = await session.scalar(
        select(Payment).where(Payment.merchant_trans_id == payload.merchant_trans_id)
    )
    order = await session.get(Order, payment.order_id) if payment else None
    if not payment or not order or order.order_number != payload.order_number:
        raise HTTPException(status_code=404, detail="payment_not_found")
    if order.user_id:
        user = await _optional_user(request, session)
        if not user or user.id != order.user_id:
            raise HTTPException(status_code=403, detail="forbidden")
    elif (
        not order.guest_access_token
        or not payload.access_token
        or not hmac.compare_digest(payload.access_token, order.guest_access_token)
    ):
        raise HTTPException(status_code=403, detail="forbidden")
    provider = get_provider()
    service = PaymentService(session, provider)
    return await run_scenario(session, provider, service, payment, payload.scenario)
