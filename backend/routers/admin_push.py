"""Only active administrators may register or test their current device."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from auth import csrf_protect, require_roles
from admin_push import (
    endpoint_hash,
    enqueue_admin_notification,
    public_key,
    valid_endpoint,
    valid_key,
)
from db.models import AdminPushSubscription, User, uid, utcnow
from db.session import get_session

router = APIRouter(prefix="/api/v1/admin/push", tags=["admin-push"])
require_admin = require_roles("admin")


class KeysIn(BaseModel):
    p256dh: str = Field(max_length=100)
    auth: str = Field(max_length=32)


class EndpointIn(BaseModel):
    endpoint: str = Field(min_length=1, max_length=4096)


class SubscriptionIn(EndpointIn):
    keys: KeysIn


@router.get("/config")
async def config(_user: User = Depends(require_admin)):
    key = public_key()
    return {"enabled": bool(key), "public_key": key}


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
