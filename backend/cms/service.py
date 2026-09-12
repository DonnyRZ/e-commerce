"""CMS domain service — serialization, revisions, audit, preview tokens,
content safety (URL validation + script rejection)."""

import hashlib
import hmac
import os
import re
import time
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    CmsAuditLog,
    CmsContentEntry,
    CmsContentTranslation,
    CmsMediaAsset,
    CmsRevision,
)
from storage import get_media_storage

LOCALES = ("id", "en", "uz", "ru")

CONTENT_TYPES = (
    "hero", "announcement", "banner", "story", "page", "faq_item",
    "nav_item", "footer_group", "footer_item", "footer_text",
    "homepage_section", "department_visual",
)

REVISION_ACTIONS = ("created", "saved_draft", "published", "unpublished", "archived", "restored")

_STATUS_TRANSITIONS = {
    "publish": {"draft", "archived"},
    "unpublish": {"published"},
    "archive": {"draft", "published"},
}

_SAFE_URL = re.compile(r"^(/[^\s]*|https?://[^\s]+)$", re.IGNORECASE)
_UNSAFE_TEXT = re.compile(r"<\s*(script|iframe)|javascript:|data:text/html|on\w+\s*=", re.IGNORECASE)


def validate_url(url: Optional[str]) -> Optional[str]:
    """Allow safe internal routes and http(s) URLs; reject dangerous protocols."""
    if url in (None, ""):
        return None
    url = url.strip()
    if len(url) > 500 or not _SAFE_URL.match(url):
        raise ValueError("invalid_url")
    return url


def sanitize_text(value: Optional[str], max_len: int = 10000) -> str:
    """CMS text is rendered as plain text by React (never raw HTML); we still
    reject script-bearing content at the boundary."""
    if value is None:
        return ""
    if len(value) > max_len or _UNSAFE_TEXT.search(value):
        raise ValueError("unsafe_content")
    return value


def validate_payload(payload: dict) -> None:
    """Reject legacy/external image URLs from CMS content payloads."""

    if not isinstance(payload, dict):
        raise ValueError("invalid_payload")
    image_url = payload.get("image_url")
    if image_url in (None, ""):
        return
    if (
        not isinstance(image_url, str)
        or len(image_url) > 500
        or not image_url.startswith("/")
        or image_url.startswith("//")
    ):
        raise ValueError("invalid_media_url")


def clean_payload(payload: Optional[dict]) -> dict:
    """Keep only local legacy image fallbacks in serialized CMS payloads."""

    result = dict(payload or {})
    image_url = result.get("image_url")
    if image_url not in (None, "") and (
        not isinstance(image_url, str)
        or not image_url.startswith("/")
        or image_url.startswith("//")
    ):
        result.pop("image_url", None)
    return result


def _signing_key() -> str:
    return os.environ["JWT_SECRET"]


def make_preview_token(entry_id: str, ttl_seconds: int = 3600) -> str:
    exp = int(time.time()) + ttl_seconds
    msg = f"{entry_id}.{exp}"
    sig = hmac.new(_signing_key().encode(), msg.encode(), hashlib.sha256).hexdigest()
    return f"{msg}.{sig}"


def verify_preview_token(token: str) -> Optional[str]:
    try:
        entry_id, exp, sig = token.rsplit(".", 2)
        if int(exp) < int(time.time()):
            return None
        msg = f"{entry_id}.{exp}"
        expected = hmac.new(_signing_key().encode(), msg.encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, expected):
            return entry_id
    except (ValueError, AttributeError):
        return None
    return None


def status_transition_allowed(current: str, action: str) -> Optional[str]:
    allowed_from = _STATUS_TRANSITIONS.get(action)
    if not allowed_from or current not in allowed_from:
        return None
    return {"publish": "published", "unpublish": "draft", "archive": "archived"}[action]


async def audit(session: AsyncSession, actor_id: Optional[str], action: str,
                target_type: str, target_id: str, meta: Optional[dict] = None) -> None:
    session.add(
        CmsAuditLog(
            actor_user_id=actor_id, action=action,
            target_type=target_type, target_id=target_id, safe_metadata=meta,
        )
    )


async def snapshot_entry(session: AsyncSession, entry: CmsContentEntry) -> dict:
    translations = (
        await session.execute(
            select(CmsContentTranslation).where(CmsContentTranslation.entry_id == entry.id)
        )
    ).scalars().all()
    return {
        "content_type": entry.content_type,
        "internal_name": entry.internal_name,
        "slug": entry.slug,
        "placement": entry.placement,
        "sort_order": entry.sort_order,
        "is_visible": entry.is_visible,
        "media_id": entry.media_id,
        "cta_url": entry.cta_url,
        "secondary_cta_url": entry.secondary_cta_url,
        "payload": entry.payload or {},
        "translations": {
            t.locale: {
                "title": t.title, "eyebrow": t.eyebrow, "subtitle": t.subtitle,
                "description": t.description, "body": t.body,
                "cta_label": t.cta_label, "secondary_cta_label": t.secondary_cta_label,
                "alt_text": t.alt_text,
            }
            for t in translations
        },
    }


async def add_revision(session: AsyncSession, entry: CmsContentEntry, action: str,
                       actor_id: Optional[str]) -> None:
    current_max = await session.scalar(
        select(func.coalesce(func.max(CmsRevision.version_number), 0)).where(
            CmsRevision.content_id == entry.id
        )
    )
    session.add(
        CmsRevision(
            content_type=entry.content_type,
            content_id=entry.id,
            version_number=int(current_max or 0) + 1,
            action=action,
            snapshot=await snapshot_entry(session, entry),
            created_by=actor_id,
        )
    )


async def _media_url(session: AsyncSession, media_id: Optional[str]) -> Optional[str]:
    if not media_id:
        return None
    asset = await session.get(CmsMediaAsset, media_id)
    if not asset:
        return None
    public_url = get_media_storage().public_url(asset.storage_key)
    return public_url or f"/api/v1/cms/media/file/{asset.storage_key}"


async def media_url(session: AsyncSession, asset: CmsMediaAsset) -> str:
    """Return a browser-safe URL for an asset in local or S3 storage."""

    return get_media_storage().public_url(asset.storage_key) or (
        f"/api/v1/cms/media/file/{asset.storage_key}"
    )


async def entry_detail(session: AsyncSession, entry: CmsContentEntry) -> dict:
    translations = (
        await session.execute(
            select(CmsContentTranslation).where(CmsContentTranslation.entry_id == entry.id)
        )
    ).scalars().all()
    payload = clean_payload(entry.payload)
    image_url = await _media_url(session, entry.media_id) or payload.get("image_url")
    return {
        "id": entry.id,
        "content_type": entry.content_type,
        "internal_name": entry.internal_name,
        "slug": entry.slug,
        "status": entry.status,
        "placement": entry.placement,
        "sort_order": entry.sort_order,
        "is_visible": entry.is_visible,
        "media_id": entry.media_id,
        "image_url": image_url,
        "cta_url": entry.cta_url,
        "secondary_cta_url": entry.secondary_cta_url,
        "payload": payload,
        "published_at": entry.published_at,
        "updated_at": entry.updated_at,
        "translations": {
            t.locale: {
                "title": t.title, "eyebrow": t.eyebrow, "subtitle": t.subtitle,
                "description": t.description, "body": t.body,
                "cta_label": t.cta_label, "secondary_cta_label": t.secondary_cta_label,
                "alt_text": t.alt_text,
            }
            for t in translations
        },
        "completeness": sorted(
            t.locale for t in translations if (t.title or t.body or t.description)
        ),
    }


async def entry_summary(session: AsyncSession, entry: CmsContentEntry) -> dict:
    translations = (
        await session.execute(
            select(CmsContentTranslation.locale, CmsContentTranslation.title,
                   CmsContentTranslation.body, CmsContentTranslation.description)
            .where(CmsContentTranslation.entry_id == entry.id)
        )
    ).all()
    return {
        "id": entry.id,
        "content_type": entry.content_type,
        "internal_name": entry.internal_name,
        "slug": entry.slug,
        "status": entry.status,
        "placement": entry.placement,
        "sort_order": entry.sort_order,
        "is_visible": entry.is_visible,
        "media_id": entry.media_id,
        "updated_at": entry.updated_at,
        "completeness": sorted(
            t.locale for t in translations if (t.title or t.body or t.description)
        ),
    }


async def public_entry(session: AsyncSession, entry: CmsContentEntry) -> dict:
    detail = await entry_detail(session, entry)
    return {
        "id": detail["id"],
        "content_type": detail["content_type"],
        "slug": detail["slug"],
        "placement": detail["placement"],
        "sort_order": detail["sort_order"],
        "image_url": detail["image_url"],
        "cta_url": detail["cta_url"],
        "secondary_cta_url": detail["secondary_cta_url"],
        "payload": detail["payload"],
        "translations": detail["translations"],
    }
