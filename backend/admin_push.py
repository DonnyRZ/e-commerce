"""Encrypted Web Push, queued in the same transaction as the business event."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import secrets
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pywebpush import WebPushException, webpush
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from config import ADMIN_PUSH_ENABLED, VAPID_PRIVATE_KEY_FILE, VAPID_SUBJECT
from db.models import AdminPushDelivery, AdminPushSubscription, User, uid, utcnow
from db.session import SessionLocal

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 6
RETRY_SECONDS = (15, 60, 300, 900, 3600, 7200)


def public_key() -> str | None:
    if not ADMIN_PUSH_ENABLED:
        return None
    try:
        key = serialization.load_pem_private_key(
            Path(VAPID_PRIVATE_KEY_FILE).read_bytes(), password=None
        )
        if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(
            key.curve, ec.SECP256R1
        ):
            return None
        raw = key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    except (OSError, ValueError, TypeError):
        return None


def endpoint_hash(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode()).hexdigest()


def valid_endpoint(endpoint: str) -> bool:
    """A subscription must never make the server fetch an arbitrary URL."""
    try:
        url = urlparse(endpoint)
        host = (url.hostname or "").lower()
        allowed = (
            host
            in {
                "fcm.googleapis.com",
                "updates.push.services.mozilla.com",
                "web.push.apple.com",
            }
            or host.endswith(".notify.windows.com")
            or host.endswith(".push.apple.com")
        )
        return bool(
            allowed
            and url.scheme == "https"
            and url.port in (None, 443)
            and not url.username
            and not url.password
            and not url.fragment
            and url.path not in ("", "/")
            and len(endpoint) <= 4096
        )
    except ValueError:
        return False


def valid_key(value: str, length: int) -> bool:
    try:
        if any(
            c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-="
            for c in value
        ):
            return False
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        if length == 65:
            ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), raw)
        return len(raw) == length
    except (ValueError, TypeError):
        return False


async def enqueue_admin_notification(
    session, event_key: str, kind: str, url: str, *, subscription_id: str | None = None
) -> int:
    if not ADMIN_PUSH_ENABLED:
        return 0
    query = (
        select(AdminPushSubscription)
        .join(User, User.id == AdminPushSubscription.user_id)
        .where(
            AdminPushSubscription.enabled.is_(True),
            User.is_active.is_(True),
            User.role == "admin",
            AdminPushSubscription.token_version == User.token_version,
        )
    )
    if subscription_id:
        query = query.where(AdminPushSubscription.id == subscription_id)
    subscriptions = (await session.scalars(query)).all()
    if not subscriptions:
        return 0
    titles = {
        "telegram": "Chat Telegram baru",
        "order": "Pending order baru",
        "test": "Notifikasi CMS aktif",
    }
    bodies = {
        "telegram": "Ada pesan baru dari customer. Buka Inbox Telegram untuk membalas.",
        "order": "Ada order baru yang perlu ditindaklanjuti di CMS.",
        "test": "Perangkat ini siap menerima notifikasi chat Telegram dan order baru.",
    }
    # Lock-screen notifications intentionally contain no customer names/chat text.
    payload = {
        "title": titles[kind],
        "body": bodies[kind],
        "url": url,
        "tag": f"cms-{kind}:{url}",
        "kind": kind,
    }
    now = utcnow()
    rows = [
        {
            "id": (delivery_id := uid()),
            "subscription_id": sub.id,
            "user_id": sub.user_id,
            "token_version": sub.token_version,
            "event_key": event_key,
            "payload": {
                **payload,
                "_audit": {
                    "delivery_id": delivery_id,
                    "ack_token": secrets.token_urlsafe(32),
                },
            },
            "status": "pending",
            "attempts": 0,
            "created_at": now,
            "next_attempt_at": now,
            "expires_at": now + timedelta(hours=24),
        }
        for sub in subscriptions
    ]
    await session.execute(
        insert(AdminPushDelivery)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_admin_push_delivery_event")
    )
    return len(rows)


def send_delivery(subscription: AdminPushSubscription, payload: dict):
    return webpush(
        subscription_info={
            "endpoint": subscription.endpoint,
            "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
        },
        data=json.dumps(payload, ensure_ascii=False),
        vapid_private_key=VAPID_PRIVATE_KEY_FILE,
        vapid_claims={"sub": VAPID_SUBJECT},
        ttl=86400,
        timeout=10,
        headers={"Urgency": "high"},
    )


async def dispatch_pending(session) -> int:
    now = utcnow()
    await session.execute(
        delete(AdminPushDelivery).where(
            AdminPushDelivery.expires_at < now - timedelta(days=7)
        )
    )
    result = await session.execute(
        select(AdminPushDelivery, AdminPushSubscription)
        .join(
            AdminPushSubscription,
            AdminPushSubscription.id == AdminPushDelivery.subscription_id,
        )
        .join(User, User.id == AdminPushSubscription.user_id)
        .where(
            AdminPushDelivery.status == "pending",
            AdminPushDelivery.next_attempt_at <= now,
            AdminPushDelivery.expires_at > now,
            AdminPushDelivery.attempts < MAX_ATTEMPTS,
            AdminPushSubscription.enabled.is_(True),
            User.is_active.is_(True),
            User.role == "admin",
            AdminPushDelivery.user_id == User.id,
            AdminPushDelivery.token_version == User.token_version,
            AdminPushSubscription.token_version == User.token_version,
        )
        .order_by(AdminPushDelivery.created_at)
        .limit(20)
        .with_for_update(skip_locked=True, of=AdminPushDelivery)
    )
    rows = result.all()
    semaphore = asyncio.Semaphore(5)

    async def deliver(row, subscription):
        async with semaphore:
            row.attempts += 1
            dispatch_started_at = utcnow()
            logger.info(
                "admin_push_dispatch_started delivery_id=%s queued_at_utc=%s "
                "attempt=%s dispatch_started_at_utc=%s",
                row.id,
                row.created_at.isoformat(),
                row.attempts,
                dispatch_started_at.isoformat(),
            )
            try:
                response = await asyncio.to_thread(
                    send_delivery, subscription, row.payload
                )
                status = getattr(response, "status_code", 201)
                row.status = "sent"
                row.last_status = status
                logger.info(
                    "admin_push_provider_accepted delivery_id=%s status=%s "
                    "accepted_at_utc=%s",
                    row.id,
                    status,
                    utcnow().isoformat(),
                )
            except Exception as exc:
                response = exc.response if isinstance(exc, WebPushException) else None
                status = getattr(response, "status_code", None)
                row.last_status = status
                if status in (404, 410):
                    subscription.enabled = False
                    row.status = "expired"
                else:
                    row.status = "failed" if row.attempts >= MAX_ATTEMPTS else "pending"
                    retry = RETRY_SECONDS[row.attempts - 1]
                    try:
                        retry = (
                            max(
                                retry,
                                min(
                                    86400, int(response.headers.get("Retry-After", "0"))
                                ),
                            )
                            if response is not None
                            else retry
                        )
                    except (ValueError, TypeError):
                        pass
                    row.next_attempt_at = utcnow() + timedelta(seconds=retry)
                    logger.warning(
                        "admin_push_delivery_failed delivery_id=%s status=%s "
                        "attempt=%s failed_at_utc=%s",
                        row.id,
                        status,
                        row.attempts,
                        utcnow().isoformat(),
                    )

    await asyncio.gather(*(deliver(row, sub) for row, sub in rows))
    await session.commit()
    return len(rows)


async def admin_push_dispatch_loop():
    if not public_key():
        return
    while True:
        try:
            async with SessionLocal() as session:
                count = await dispatch_pending(session)
        except Exception:
            # Do not log provider response bodies or subscription endpoints.
            logger.warning("admin_push_dispatch_unavailable")
            count = 0
        await asyncio.sleep(1 if count else 5)
