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
from sqlalchemy import delete, event, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from config import (
    ADMIN_PUSH_ENABLED,
    FRONTEND_URL,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_STORE_USERNAME,
    VAPID_PRIVATE_KEY_FILE,
    VAPID_SUBJECT,
)
from db.models import (
    AdminPushDelivery,
    AdminPushSubscription,
    TelegramBusinessConnection,
    User,
    uid,
    utcnow,
)
from db.session import SessionLocal
from telegram_inquiries import TelegramDeliveryError, bot_request

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 6
RETRY_SECONDS = (15, 60, 300, 900, 3600, 7200)
TELEGRAM_BACKUP_DELAY = timedelta(seconds=15)
TELEGRAM_BACKUP_BATCH_SIZE = 20
_push_wakeup: asyncio.Event | None = None


@event.listens_for(Session, "after_commit")
def _wake_committed_push(session):
    # SQLAlchemy emits this only after the enclosing transaction commits.
    # A rollback must never trigger an alert for a discarded business event.
    if session.info.pop("admin_push_queued", False) and _push_wakeup is not None:
        _push_wakeup.set()


@event.listens_for(Session, "after_rollback")
def _discard_rolled_back_push(session):
    session.info.pop("admin_push_queued", None)


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
    now = utcnow()
    # Lock-screen notifications intentionally contain no customer names/chat text.
    payload = {
        "title": titles[kind],
        "body": bodies[kind],
        "url": url,
        # Each business event remains visible; retries replace only that event.
        "tag": f"cms-{kind}:{hashlib.sha256(event_key.encode()).hexdigest()[:32]}",
        "timestamp": int(now.timestamp() * 1000),
        "kind": kind,
    }
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
    session.info["admin_push_queued"] = True
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
        # Chat alerts remain useful after the phone wakes. A 60-second TTL
        # discarded undelivered messages during the observed idle delay.
        # Timestamp and per-event tag preserve which message was queued.
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


def _telegram_backup_payload(urls: str | list[str]) -> dict:
    """Create a content-free Bot API alert with validated CMS deep links."""
    urls = [urls] if isinstance(urls, str) else urls
    targets = []
    frontend = urlparse(FRONTEND_URL)
    for url in dict.fromkeys(urls):
        parsed = urlparse(url)
        if (
            parsed.scheme == ""
            and parsed.netloc == ""
            and parsed.path.startswith("/admin/")
            and frontend.scheme == "https"
            and frontend.netloc
        ):
            target = urlparse(FRONTEND_URL + "/" + url.lstrip("/"))
            if target.scheme == "https" and target.netloc == frontend.netloc:
                targets.append(target.geturl())
    message = {
        "text": (
            "📩 Pesan Telegram baru menunggu balasan di CMS."
            if len(targets) <= 1
            else "📩 Ada beberapa pesan Telegram baru yang menunggu balasan di CMS."
        )
    }
    if targets:
        message["reply_markup"] = {
            "inline_keyboard": [
                [
                    {
                        "text": "Buka chat di CMS"
                        if len(targets) == 1
                        else f"Buka chat {index + 1}",
                        "url": target,
                    }
                ]
                for index, target in enumerate(targets[:TELEGRAM_BACKUP_BATCH_SIZE])
            ]
        }
    return message


async def _send_telegram_backup(recipient_id: str, urls: list[str]) -> None:
    if not recipient_id.isdecimal() or len(recipient_id) > 20:
        raise TelegramDeliveryError("telegram_backup_recipient_unavailable")
    await bot_request(
        TELEGRAM_BOT_TOKEN,
        "sendMessage",
        {"chat_id": int(recipient_id), **_telegram_backup_payload(urls)},
        timeout_seconds=8.0,
    )


async def dispatch_telegram_fallbacks(session, *, now=None) -> int:
    """Send one free Telegram alert if no device confirmed showing the Web Push.

    The existing delivery JSON is the durable outbox state, so this does not
    require a schema migration. Every delivery for an event is marked together
    under row locks, which prevents duplicate fallback messages across workers.
    """
    now = now or utcnow()
    eligible = await session.scalars(
        select(AdminPushDelivery.event_key)
        .where(
            AdminPushDelivery.created_at <= now - TELEGRAM_BACKUP_DELAY,
            AdminPushDelivery.expires_at > now,
            AdminPushDelivery.payload["kind"].as_string() == "telegram",
            AdminPushDelivery.payload["_audit"]["telegram_fallback"]
            .as_string()
            .is_(None),
        )
        .group_by(AdminPushDelivery.event_key)
        .order_by(func.min(AdminPushDelivery.created_at))
        .limit(TELEGRAM_BACKUP_BATCH_SIZE)
    )
    event_keys = list(eligible.all())
    if not event_keys:
        return 0

    recipient_id = None
    if TELEGRAM_BOT_TOKEN:
        recipient_id = await session.scalar(
            select(TelegramBusinessConnection.business_user_id)
            .where(
                TelegramBusinessConnection.username == TELEGRAM_STORE_USERNAME,
                TelegramBusinessConnection.is_enabled.is_(True),
                TelegramBusinessConnection.can_reply.is_(True),
                TelegramBusinessConnection.can_read_messages.is_(True),
            )
            .order_by(TelegramBusinessConnection.updated_at.desc())
            .limit(1)
        )

    claimed: list[tuple[str, str]] = []
    for event_key in event_keys:
        result = await session.scalars(
            select(AdminPushDelivery)
            .where(AdminPushDelivery.event_key == event_key)
            .order_by(AdminPushDelivery.created_at, AdminPushDelivery.id)
            .with_for_update()
        )
        deliveries = list(result.all())
        if not deliveries:
            continue
        audits = [
            (delivery.payload or {}).get("_audit", {}) for delivery in deliveries
        ]
        if any(audit.get("telegram_fallback") for audit in audits):
            continue

        displayed_on_every_device = bool(audits) and all(
            "notification_show_resolved"
            in (audit.get("device_stages") or {})
            for audit in audits
        )
        status = "skipped" if displayed_on_every_device else "unavailable"
        if not displayed_on_every_device and recipient_id and TELEGRAM_BOT_TOKEN:
            status = "queued"
            url = next(
                (
                    str(delivery.payload.get("url"))
                    for delivery in deliveries
                    if isinstance(delivery.payload, dict)
                    and delivery.payload.get("url")
                ),
                "/admin/telegram-inbox",
            )
            claimed.append((event_key, url))

        marker = {"status": status, "attempted_at_utc": now.isoformat()}
        for delivery in deliveries:
            audit = dict((delivery.payload or {}).get("_audit", {}))
            audit["telegram_fallback"] = marker
            delivery.payload = {**(delivery.payload or {}), "_audit": audit}
    await session.commit()

    outcomes = []
    if claimed:
        try:
            # Batch alerts generated in the same worker pass into one Telegram
            # message. This stays within ordinary Bot API rate limits and puts
            # a direct CMS link for each affected conversation in that alert.
            await _send_telegram_backup(
                str(recipient_id), [url for _, url in claimed]
            )
            status, error_code = "sent", None
        except TelegramDeliveryError as exc:
            status, error_code = "failed", exc.safe_code
        except TimeoutError:
            # The Bot API outcome may be ambiguous; do not blindly duplicate.
            status, error_code = "unknown", "telegram_delivery_outcome_unknown"
        except Exception:
            status, error_code = "failed", "telegram_backup_unavailable"
        outcomes = [
            (event_key, status, error_code) for event_key, _ in claimed
        ]
    sent = 0
    for event_key, status, error_code in outcomes:
        result = await session.scalars(
            select(AdminPushDelivery).where(
                AdminPushDelivery.event_key == event_key
            ).with_for_update()
        )
        for delivery in result.all():
            payload = dict(delivery.payload or {})
            audit = dict(payload.get("_audit", {}))
            audit["telegram_fallback"] = {
                "status": status,
                "attempted_at_utc": now.isoformat(),
                "completed_at_utc": utcnow().isoformat(),
                **({"error_code": error_code} if error_code else {}),
            }
            payload["_audit"] = audit
            delivery.payload = payload
        if status == "sent":
            sent += 1
            logger.info("admin_push_telegram_backup_sent event_key=%s", event_key)
        else:
            logger.warning(
                "admin_push_telegram_backup_failed event_key=%s status=%s code=%s",
                event_key,
                status,
                error_code or "telegram_backup_unavailable",
            )
    if outcomes:
        await session.commit()
    return sent


async def _web_push_loop():
    global _push_wakeup
    _push_wakeup = asyncio.Event()
    try:
        while True:
            _push_wakeup.clear()
            try:
                async with SessionLocal() as session:
                    await dispatch_pending(session)
            except Exception:
                # Never log provider bodies or subscription endpoints.
                logger.warning("admin_push_dispatch_unavailable")
            try:
                # Commits in this process wake us immediately; the one-second
                # scan also picks up events written by another process.
                await asyncio.wait_for(_push_wakeup.wait(), timeout=1)
            except asyncio.TimeoutError:
                pass
    finally:
        _push_wakeup = None


async def _telegram_backup_loop():
    while True:
        try:
            async with SessionLocal() as session:
                await dispatch_telegram_fallbacks(session)
        except Exception:
            logger.warning("admin_push_telegram_backup_unavailable")
        # A slow Telegram API request cannot hold up new native Web Push.
        await asyncio.sleep(1)


async def admin_push_dispatch_loop():
    if not public_key():
        return
    await asyncio.gather(_web_push_loop(), _telegram_backup_loop())
