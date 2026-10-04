"""Only active administrators may register or test their current device."""

import hmac
import logging
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from auth import csrf_protect, require_roles
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_USERNAME
from admin_push import (
    endpoint_hash,
    enqueue_admin_notification,
    public_key,
    valid_endpoint,
    valid_key,
)
from db.models import AdminPushDelivery, AdminPushSubscription, User, uid, utcnow
from db.session import get_session

router = APIRouter(prefix="/api/v1/admin/push", tags=["admin-push"])
require_admin = require_roles("admin")
logger = logging.getLogger(__name__)


class KeysIn(BaseModel):
    p256dh: str = Field(max_length=100)
    auth: str = Field(max_length=32)


class EndpointIn(BaseModel):
    endpoint: str = Field(min_length=1, max_length=4096)


class SubscriptionIn(EndpointIn):
    keys: KeysIn


class DeliveryAckIn(BaseModel):
    delivery_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    ack_token: str = Field(min_length=43, max_length=43)
    client_started_at: AwareDatetime | None = None
    client_observed_at: AwareDatetime | None = None
    event_elapsed_ms: int | None = Field(default=None, ge=0, le=86_400_000)
    worker_version: str | None = Field(default=None, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    stage: Literal[
        "push_received",
        "notification_show_resolved",
        "notification_show_failed",
    ]


@router.post("/delivery-ack", status_code=204, response_class=Response)
async def delivery_ack(payload: DeliveryAckIn, session=Depends(get_session)):
    """Accept a one-delivery bearer acknowledgment from the service worker."""
    # Concurrent receipt/display ACKs and Telegram fallback update this JSON.
    # Serialize merges so one update cannot erase another observation.
    delivery = await session.scalar(
        select(AdminPushDelivery)
        .where(AdminPushDelivery.id == payload.delivery_id)
        .with_for_update()
    )
    audit = (delivery.payload or {}).get("_audit", {}) if delivery else {}
    saved_token = audit.get("ack_token", "")
    if (
        delivery
        and isinstance(saved_token, str)
        and hmac.compare_digest(saved_token, payload.ack_token)
    ):
        observed_at = utcnow().isoformat()
        device_stages = dict(audit.get("device_stages", {}))
        # Keep the first observation for each stage so delivery timing stays
        # useful even if a service worker retries its acknowledgment.
        device_stages.setdefault(payload.stage, observed_at)
        device_timings = dict(audit.get("device_timings", {}))
        timing = {
            "client_started_at": payload.client_started_at.isoformat() if payload.client_started_at else None,
            "client_observed_at": payload.client_observed_at.isoformat() if payload.client_observed_at else None,
            "event_elapsed_ms": payload.event_elapsed_ms,
            "worker_version": payload.worker_version,
        }
        if payload.client_started_at is not None:
            device_timings.setdefault(payload.stage, timing)
        audit = {**audit, "device_stages": device_stages, "device_timings": device_timings}
        delivery.payload = {**(delivery.payload or {}), "_audit": audit}
        await session.commit()
        logger.info(
            "admin_push_device_stage delivery_id=%s stage=%s observed_at_utc=%s client_started_at=%s client_observed_at=%s event_elapsed_ms=%s worker_version=%s",
            delivery.id,
            payload.stage,
            observed_at,
            timing["client_started_at"],
            timing["client_observed_at"],
            payload.event_elapsed_ms,
            payload.worker_version,
        )
    # Keep invalid and unknown delivery IDs indistinguishable. The token is
    # random, single-delivery scope, and never written to logs.
    return Response(status_code=204)


@router.get("/config")
async def config(_user: User = Depends(require_admin)):
    key = public_key()
    bot_username = TELEGRAM_BOT_USERNAME.strip().lstrip("@").lower()
    telegram_backup_url = (
        f"https://t.me/{bot_username}?start=cms_push_backup"
        if TELEGRAM_BOT_TOKEN and re.fullmatch(r"[a-z0-9_]{5,32}", bot_username)
        else None
    )
    return {
        "enabled": bool(key),
        "public_key": key,
        "telegram_backup_url": telegram_backup_url,
    }


@router.post("/subscriptions", dependencies=[Depends(csrf_protect)])
async def subscribe(
    payload: SubscriptionIn,
    user: User = Depends(require_admin),
    session=Depends(get_session),
):
    if not public_key():
        raise HTTPException(503, detail="push_not_configured")
    if (
        not valid_endpoint(payload.endpoint)
        or not valid_key(payload.keys.p256dh, 65)
        or not valid_key(payload.keys.auth, 16)
    ):
        raise HTTPException(422, detail="invalid_push_subscription")
    hashed = endpoint_hash(payload.endpoint)
    existing = await session.scalar(
        select(AdminPushSubscription).where(
            AdminPushSubscription.endpoint_hash == hashed
        )
    )
    if existing and not existing.enabled:
        # The push service returned 404/410 for this endpoint. Reusing it would
        # silently revive a dead subscription, so ask the client to renew it.
        return {"enabled": False, "replace": True}
    if not existing:
        count = await session.scalar(
            select(func.count())
            .select_from(AdminPushSubscription)
            .where(
                AdminPushSubscription.user_id == user.id,
                AdminPushSubscription.enabled.is_(True),
            )
        )
        if count >= 50:
            raise HTTPException(409, detail="push_device_limit")
    now = utcnow()
    values = dict(
        user_id=user.id,
        endpoint=payload.endpoint,
        p256dh=payload.keys.p256dh,
        auth=payload.keys.auth,
        token_version=user.token_version,
        enabled=True,
        updated_at=now,
    )
    statement = insert(AdminPushSubscription).values(
        id=uid(), endpoint_hash=hashed, created_at=now, **values
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[AdminPushSubscription.endpoint_hash], set_=values
        )
    )
    await session.commit()
    return {"enabled": True}


@router.delete("/subscriptions", dependencies=[Depends(csrf_protect)])
async def unsubscribe(
    payload: EndpointIn,
    user: User = Depends(require_admin),
    session=Depends(get_session),
):
    subscription = await session.scalar(
        select(AdminPushSubscription).where(
            AdminPushSubscription.endpoint_hash == endpoint_hash(payload.endpoint),
            AdminPushSubscription.user_id == user.id,
        )
    )
    if subscription:
        subscription.enabled = False
    await session.commit()
    return {"enabled": False}


@router.post("/test", dependencies=[Depends(csrf_protect)])
async def test_notification(
    payload: EndpointIn,
    user: User = Depends(require_admin),
    session=Depends(get_session),
):
    if not public_key():
        raise HTTPException(503, detail="push_not_configured")
    subscription = await session.scalar(
        select(AdminPushSubscription).where(
            AdminPushSubscription.endpoint_hash == endpoint_hash(payload.endpoint),
            AdminPushSubscription.user_id == user.id,
            AdminPushSubscription.enabled.is_(True),
            AdminPushSubscription.token_version == user.token_version,
        )
    )
    if not subscription:
        raise HTTPException(404, detail="push_device_not_registered")
    await enqueue_admin_notification(
        session,
        "test:" + uid(),
        "test",
        "/admin/settings",
        subscription_id=subscription.id,
    )
    await session.commit()
    return {"queued": True}
