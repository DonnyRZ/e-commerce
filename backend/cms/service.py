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

HOMEPAGE_SECTION_KEYS = (
    "promo_bar", "hero", "categories", "new_arrivals",
    "departments", "best_sellers", "curated_primary",
    "curated_secondary", "stories", "footer",
)

REVISION_ACTIONS = ("created", "saved_draft", "published", "unpublished", "archived", "restored")

_STATUS_TRANSITIONS = {
    "publish": {"draft", "published", "archived"},
    "unpublish": {"published"},
    "archive": {"draft", "published"},
}

_SAFE_URL = re.compile(r"^(/[^\s]*|https?://[^\s]+|mailto:[^@\s]+@[^@\s]+)$", re.IGNORECASE)
_UNSAFE_TEXT = re.compile(r"<\s*(script|iframe)|javascript:|data:text/html|on\w+\s*=", re.IGNORECASE)


def validate_url(url: Optional[str]) -> Optional[str]:
    """Allow safe internal routes and http(s) URLs; reject dangerous protocols."""
    if url in (None, ""):
        return None
    url = url.strip()
    if len(url) > 500 or url.startswith("//") or not _SAFE_URL.match(url):
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


def _is_local_image_url(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= 500
        and value.startswith("/")
        and not value.startswith("//")
    )


def _walk_payload(value: object):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key, nested
            yield from _walk_payload(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_payload(nested)


def validate_payload(payload: dict) -> None:
    """Reject external image URLs at every nested CMS payload level."""

    if not isinstance(payload, dict):
        raise ValueError("invalid_payload")
    for key, value in _walk_payload(payload):
        if key == "image_url" and value not in (None, "") and not _is_local_image_url(value):
            raise ValueError("invalid_media_url")


def clean_payload(payload: Optional[dict]) -> dict:
    """Remove invalid nested legacy image fallbacks from serialized payloads."""

    def clean(value):
        if isinstance(value, dict):
            result = {}
            for key, nested in value.items():
                if (
                    key == "image_url"
                    and nested not in (None, "")
                    and not _is_local_image_url(nested)
                ):
                    continue
                result[key] = clean(nested)
            return result
        if isinstance(value, list):
            return [clean(nested) for nested in value]
        return value

    return clean(payload or {})


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


def apply_snapshot(entry: CmsContentEntry, snapshot: dict) -> None:
    """Apply a validated content snapshot to its live database row."""
    for field in (
        "internal_name", "slug", "placement", "sort_order", "is_visible",
        "media_id", "cta_url", "secondary_cta_url",
    ):
        if field in snapshot:
            setattr(entry, field, snapshot[field])
    if "payload" in snapshot:
        entry.payload = clean_payload(snapshot.get("payload"))


def publish_missing_fields(content_type: str, snapshot: dict) -> list[str]:
    """Return human-readable English/content requirements for publishing."""
    translations = snapshot.get("translations") or {}
    english = translations.get("en") or {}
    missing: list[str] = []
    if not str(snapshot.get("slug") or "").strip():
        missing.append("slug")
    primary_field = "alt_text" if content_type == "department_visual" else "title"
    if not str(english.get(primary_field) or "").strip():
        missing.append(f"translations.en.{primary_field}")

    if content_type == "page" and not str(
        english.get("body") or english.get("description") or ""
    ).strip():
        missing.append("translations.en.body")
    elif content_type == "faq_item" and not str(english.get("body") or "").strip():
        missing.append("translations.en.body")
    elif content_type == "nav_item" and not snapshot.get("cta_url"):
        missing.append("cta_url")
    elif content_type == "footer_item":
        if not snapshot.get("cta_url"):
            missing.append("cta_url")
        if not str((snapshot.get("payload") or {}).get("group") or "").strip():
            missing.append("payload.group")
    elif content_type == "homepage_section":
        if snapshot.get("slug") not in HOMEPAGE_SECTION_KEYS:
            missing.append("slug")
    elif content_type == "department_visual":
        if not snapshot.get("slug"):
            missing.append("slug")
        if not snapshot.get("media_id"):
            missing.append("media_id")

    return missing


async def add_revision(session: AsyncSession, entry: CmsContentEntry, action: str,
                       actor_id: Optional[str], snapshot_override: Optional[dict] = None) -> None:
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
            snapshot=snapshot_override if snapshot_override is not None else await snapshot_entry(session, entry),
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
    result = {
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
            t.locale for t in translations
            if any(
                getattr(t, field)
                for field in (
                    "title",
                    "eyebrow",
                    "subtitle",
                    "body",
                    "description",
                    "cta_label",
                    "secondary_cta_label",
                    "alt_text",
                )
            )
        ),
        "has_unpublished_changes": entry.draft_snapshot is not None,
    }
    if entry.draft_snapshot is not None:
        working = dict(entry.draft_snapshot)
        working_payload = clean_payload(working.get("payload"))
        working["payload"] = working_payload
        working["image_url"] = (
            await _media_url(session, working.get("media_id"))
            or working_payload.get("image_url")
        )
        result["working_copy"] = working
    else:
        result["working_copy"] = None
    return result


async def entry_summary(session: AsyncSession, entry: CmsContentEntry) -> dict:
    translations = (
        await session.execute(
            select(
                CmsContentTranslation.locale,
                CmsContentTranslation.title,
                CmsContentTranslation.eyebrow,
                CmsContentTranslation.subtitle,
                CmsContentTranslation.body,
                CmsContentTranslation.description,
                CmsContentTranslation.cta_label,
                CmsContentTranslation.secondary_cta_label,
                CmsContentTranslation.alt_text,
            )
            .where(CmsContentTranslation.entry_id == entry.id)
        )
    ).all()
    completeness = sorted(
        t.locale for t in translations
        if any(
            getattr(t, field)
            for field in (
                "title",
                "eyebrow",
                "subtitle",
                "body",
                "description",
                "cta_label",
                "secondary_cta_label",
                "alt_text",
            )
        )
    )
    if entry.draft_snapshot is not None:
        completeness = sorted(
            locale for locale, tr in (entry.draft_snapshot.get("translations") or {}).items()
            if any(
                tr.get(field)
                for field in (
                    "title",
                    "eyebrow",
                    "subtitle",
                    "body",
                    "description",
                    "cta_label",
                    "secondary_cta_label",
                    "alt_text",
                )
            )
        )
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
        "completeness": completeness,
        "has_unpublished_changes": entry.draft_snapshot is not None,
    }


async def public_entry(session: AsyncSession, entry: CmsContentEntry,
                       use_working_copy: bool = False) -> dict:
    detail = await entry_detail(session, entry)
    if use_working_copy and detail.get("working_copy"):
        detail = {**detail, **detail["working_copy"]}
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
