"""CMS admin API — content CRUD, draft/publish/archive, preview tokens,
revisions, media library. Admin role only; CSRF on mutations; all text
sanitized and URLs validated; mass-assignment safe (status/workflow fields
are never settable through the content payload).
"""

import hashlib
import re
import unicodedata
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import csrf_protect, require_roles
from cms import service as cms
from db.models import (
    CmsContentEntry,
    CmsContentTranslation,
    CmsMediaAsset,
    CmsMediaTranslation,
    CmsRevision,
    Category,
    Product,
    ProductVariant,
    User,
)
from db.session import get_session
from media import media_item_url
from storage import get_media_storage

router = APIRouter(prefix="/api/v1/admin/cms", tags=["admin-cms"])

require_admin = require_roles("admin")

_SLUG = re.compile(r"^[a-z0-9][a-z0-9\-]{0,158}$")

ALLOWED_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
# Keep the application limit aligned with the production reverse proxy. 4K
# product photography can legitimately exceed 15 MiB. This limit applies only
# to the authenticated CMS media endpoint.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class CmsTranslationIn(BaseModel):
    title: str = Field(default="", max_length=500)
    eyebrow: str = Field(default="", max_length=255)
    subtitle: str = Field(default="", max_length=500)
    description: str = Field(default="", max_length=10000)
    body: str = Field(default="", max_length=10000)
    cta_label: str = Field(default="", max_length=120)
    secondary_cta_label: str = Field(default="", max_length=120)
    alt_text: str = Field(default="", max_length=255)


class CmsContentIn(BaseModel):
    content_type: str
    internal_name: str = Field(min_length=1, max_length=255)
    slug: str = Field(default="", max_length=160)
    placement: str = Field(default="", max_length=80)
    sort_order: int = Field(default=0, ge=0, le=100000)
    is_visible: bool = True
    media_id: Optional[str] = Field(default=None, max_length=40)
    cta_url: Optional[str] = Field(default=None, max_length=500)
    secondary_cta_url: Optional[str] = Field(default=None, max_length=500)
    payload: dict = Field(default_factory=dict)
    translations: dict[str, CmsTranslationIn] = Field(default_factory=dict)


class CmsContentPatchIn(BaseModel):
    internal_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    slug: Optional[str] = Field(default=None, max_length=160)
    placement: Optional[str] = Field(default=None, max_length=80)
    sort_order: Optional[int] = Field(default=None, ge=0, le=100000)
    is_visible: Optional[bool] = None
    media_id: Optional[str] = Field(default=None, max_length=40)
    cta_url: Optional[str] = None
    secondary_cta_url: Optional[str] = None
    payload: Optional[dict] = None
    translations: Optional[dict[str, CmsTranslationIn]] = None


class StatusIn(BaseModel):
    action: str  # publish | unpublish | archive


class CmsMediaTranslationIn(BaseModel):
    alt_text: str = Field(default="", max_length=255)
    caption: str = Field(default="", max_length=500)


class MediaPatchIn(BaseModel):
    translations: dict[str, CmsMediaTranslationIn] = Field(default_factory=dict)


def _validate_payload_strings(value) -> None:
    if isinstance(value, str):
        cms.sanitize_text(value)
    elif isinstance(value, dict):
        for nested in value.values():
            _validate_payload_strings(nested)
    elif isinstance(value, list):
        for nested in value:
            _validate_payload_strings(nested)
    elif value is not None and not isinstance(value, (bool, int, float)):
        raise ValueError("invalid_payload")


def _validate_content(content_type: str, slug: str, translations: dict,
                      cta_url: Optional[str], secondary_cta_url: Optional[str],
                      media_id: Optional[str], payload: Optional[dict] = None) -> None:
    if content_type not in cms.CONTENT_TYPES:
        raise HTTPException(status_code=400, detail={"error": "invalid_content_type"})
    if slug and not _SLUG.match(slug):
        raise HTTPException(status_code=400, detail={"error": "invalid_slug"})
    unknown = set(translations) - set(cms.LOCALES)
    if unknown:
        raise HTTPException(status_code=400, detail={"error": "invalid_locale", "locales": sorted(unknown)})
    try:
        cms.validate_payload(payload or {})
        _validate_payload_strings(payload or {})
        cms.validate_url(cta_url)
        cms.validate_url(secondary_cta_url)
        for tr in translations.values():
            values = tr if isinstance(tr, dict) else tr.model_dump(exclude_unset=True)
            for value in values.values():
                cms.sanitize_text(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)})
    if media_id is not None and len(media_id) > 40:
        raise HTTPException(status_code=400, detail={"error": "invalid_media"})


def _generated_slug(content_type: str, internal_name: str) -> str:
    normalized = unicodedata.normalize("NFKD", internal_name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")[:140].rstrip("-")
    return slug or f"{content_type}-{uuid.uuid4().hex[:10]}"


async def _ensure_unique_slug(session: AsyncSession, content_type: str, slug: str,
                              entry_id: Optional[str] = None) -> None:
    if not slug:
        return
    # Content slugs have no global uniqueness constraint because the CMS
    # intentionally scopes them by content type. Serialize the check-and-
    # insert/update pair so two operators cannot publish the same scoped slug
    # at the same time.
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(f"cms:slug:{content_type}:{slug}")))
    )
    query = select(CmsContentEntry.id).where(
        CmsContentEntry.content_type == content_type,
        CmsContentEntry.slug == slug,
    )
    if entry_id:
        query = query.where(CmsContentEntry.id != entry_id)
    if await session.scalar(query.limit(1)):
        raise HTTPException(status_code=409, detail={"error": "duplicate_slug"})


async def _validate_references(session: AsyncSession, content_type: str, slug: str,
                               payload: dict, media_id: Optional[str]) -> None:
    if media_id:
        asset = await session.scalar(
            select(CmsMediaAsset)
            .where(CmsMediaAsset.id == media_id)
            .with_for_update()
        )
        if not asset:
            raise HTTPException(status_code=400, detail={"error": "invalid_media"})
    if content_type == "homepage_section" and slug and slug not in cms.HOMEPAGE_SECTION_KEYS:
        raise HTTPException(status_code=400, detail={"error": "invalid_homepage_section"})
    if content_type == "footer_item":
        group = (payload or {}).get("group")
        if group and not await session.scalar(
            select(CmsContentEntry.id).where(
                CmsContentEntry.content_type == "footer_group",
                CmsContentEntry.slug == group,
                CmsContentEntry.status != "archived",
            )
        ):
            raise HTTPException(status_code=400, detail={"error": "invalid_footer_group"})
    if content_type == "department_visual" and slug and not await session.scalar(
            select(Category.id).where(
                Category.kind == "department",
                Category.slug == slug,
                Category.parent_id.is_(None),
            )
    ):
        raise HTTPException(status_code=400, detail={"error": "invalid_department"})


async def _footer_group_in_use(session: AsyncSession, slug: str) -> bool:
    if not slug:
        return False
    items = (
        await session.execute(
            select(CmsContentEntry).where(
                CmsContentEntry.content_type == "footer_item",
                CmsContentEntry.status != "archived",
            )
        )
    ).scalars().all()
    return any(
        (item.payload or {}).get("group") == slug
        or ((item.draft_snapshot or {}).get("payload") or {}).get("group") == slug
        for item in items
    )


async def _validate_publish(session: AsyncSession, content_type: str, snapshot: dict,
                            entry_id: str) -> None:
    missing = cms.publish_missing_fields(content_type, snapshot)
    if missing:
        raise HTTPException(
            status_code=400,
            detail={"error": "incomplete_english", "missing": missing},
        )
    slug = str(snapshot.get("slug") or "")
    await _ensure_unique_slug(session, content_type, slug, entry_id)
    await _validate_references(
        session, content_type, slug, snapshot.get("payload") or {}, snapshot.get("media_id")
    )
    if content_type in ("hero", "announcement"):
        # Only one visible published hero/announcement is meaningful to the
        # storefront bundle. A type-scoped advisory lock closes the race where
        # two publish requests both observe no active entry.
        await session.execute(
            select(func.pg_advisory_xact_lock(func.hashtext(f"cms:published:{content_type}")))
        )
        active_entry = await session.scalar(
            select(CmsContentEntry.id).where(
                CmsContentEntry.content_type == content_type,
                CmsContentEntry.status == "published",
                CmsContentEntry.is_visible.is_(True),
                CmsContentEntry.id != entry_id,
            ).limit(1)
        )
        if active_entry:
            raise HTTPException(
                status_code=409,
                detail={"error": f"{content_type}_already_published"},
            )
    if content_type == "footer_item":
        group = (snapshot.get("payload") or {}).get("group")
        valid_group = await session.scalar(
            select(CmsContentEntry.id).where(
                CmsContentEntry.content_type == "footer_group",
                CmsContentEntry.slug == group,
                CmsContentEntry.status == "published",
                CmsContentEntry.is_visible.is_(True),
            )
        )
        if not valid_group:
            raise HTTPException(status_code=400, detail={"error": "footer_group_not_published"})
    if content_type == "footer_group":
        current = await session.get(CmsContentEntry, entry_id)
        if current and snapshot.get("slug") != current.slug and await _footer_group_in_use(session, current.slug):
            raise HTTPException(status_code=409, detail={"error": "footer_group_in_use"})
    if content_type == "department_visual":
        if not await session.scalar(
            select(Category.id).where(
                Category.kind == "department", Category.slug == slug,
                Category.parent_id.is_(None),
                Category.is_active.is_(True),
            )
        ):
            raise HTTPException(status_code=400, detail={"error": "invalid_department"})


async def _get_entry(session: AsyncSession, entry_id: str,
                     lock: bool = False) -> CmsContentEntry:
    if lock:
        entry = await session.scalar(
            select(CmsContentEntry)
            .where(CmsContentEntry.id == entry_id)
            .with_for_update()
        )
    else:
        entry = await session.get(CmsContentEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="content_not_found")
    return entry


async def _upsert_translations(session: AsyncSession, entry_id: str, translations: dict) -> None:
    existing = {
        t.locale: t
        for t in (
            await session.execute(
                select(CmsContentTranslation).where(CmsContentTranslation.entry_id == entry_id)
            )
        ).scalars().all()
    }
    for locale, tr in translations.items():
        values = tr.model_dump(exclude_unset=True) if hasattr(tr, "model_dump") else tr
        if locale in existing:
            row = existing[locale]
            for key, value in values.items():
                setattr(row, key, value)
        else:
            session.add(CmsContentTranslation(entry_id=entry_id, locale=locale, **values))


async def _replace_translations(session: AsyncSession, entry_id: str, translations: dict) -> None:
    rows = (
        await session.execute(
            select(CmsContentTranslation).where(CmsContentTranslation.entry_id == entry_id)
        )
    ).scalars().all()
    keep = set(translations)
    for row in rows:
        if row.locale not in keep:
            await session.delete(row)
    await _upsert_translations(session, entry_id, translations)


# ------------------------------ content -----------------------------------


@router.get("/content")
async def list_content(
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    type: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
):
    query = select(CmsContentEntry)
    count_q = select(func.count(CmsContentEntry.id))
    if type:
        if type not in cms.CONTENT_TYPES:
            raise HTTPException(status_code=400, detail={"error": "invalid_content_type"})
        query = query.where(CmsContentEntry.content_type == type)
        count_q = count_q.where(CmsContentEntry.content_type == type)
    if status:
        if status not in ("draft", "published", "archived"):
            raise HTTPException(status_code=400, detail={"error": "invalid_status"})
        query = query.where(CmsContentEntry.status == status)
        count_q = count_q.where(CmsContentEntry.status == status)
    if q:
        like = f"%{q}%"
        query = query.where(
            (CmsContentEntry.internal_name.ilike(like)) | (CmsContentEntry.slug.ilike(like))
        )
        count_q = count_q.where(
            (CmsContentEntry.internal_name.ilike(like)) | (CmsContentEntry.slug.ilike(like))
        )
    total = await session.scalar(count_q)
    rows = (
        await session.execute(
            query.order_by(CmsContentEntry.content_type, CmsContentEntry.sort_order,
                           CmsContentEntry.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    items = [await cms.entry_summary(session, r) for r in rows]
    return {"items": items, "total": int(total or 0), "page": page, "page_size": page_size}


@router.post("/content", status_code=201)
async def create_content(
    payload: CmsContentIn,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    _validate_content(payload.content_type, payload.slug, payload.translations,
                      payload.cta_url, payload.secondary_cta_url, payload.media_id,
                      payload.payload)
    slug = payload.slug.strip()
    if not slug and payload.content_type not in ("homepage_section", "department_visual"):
        slug = _generated_slug(payload.content_type, payload.internal_name)
    await _ensure_unique_slug(session, payload.content_type, slug)
    await _validate_references(session, payload.content_type, slug, payload.payload, payload.media_id)
    entry = CmsContentEntry(
        content_type=payload.content_type,
        internal_name=payload.internal_name,
        slug=slug,
        status="draft",
        placement=payload.placement,
        sort_order=payload.sort_order,
        is_visible=payload.is_visible,
        media_id=payload.media_id,
        cta_url=cms.validate_url(payload.cta_url),
        secondary_cta_url=cms.validate_url(payload.secondary_cta_url),
        payload=payload.payload,
        created_by=user.id,
        updated_by=user.id,
    )
    session.add(entry)
    await session.flush()
    await _upsert_translations(session, entry.id, payload.translations)
    await cms.add_revision(session, entry, "created", user.id)
    await cms.audit(session, user.id, "cms.content.create", entry.content_type, entry.id,
                    {"name": entry.internal_name})
    await session.commit()
    return await cms.entry_detail(session, entry)


@router.get("/content/{entry_id}")
async def get_content(
    entry_id: str,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    return await cms.entry_detail(session, await _get_entry(session, entry_id))


@router.patch("/content/{entry_id}")
async def update_content(
    entry_id: str,
    payload: CmsContentPatchIn,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    entry = await _get_entry(session, entry_id, lock=True)
    data = payload.model_dump(exclude_unset=True)
    translations = data.pop("translations", None)
    if "translations" in payload.model_fields_set and translations is None:
        raise HTTPException(status_code=400, detail={"error": "invalid_translations"})
    nullable_fields = {"media_id", "cta_url", "secondary_cta_url"}
    for field, value in data.items():
        if value is None and field not in nullable_fields:
            raise HTTPException(status_code=400, detail={"error": "invalid_null", "field": field})

    use_working_copy = entry.status == "published" or entry.draft_snapshot is not None
    if use_working_copy:
        working = dict(entry.draft_snapshot or await cms.snapshot_entry(session, entry))
        working["translations"] = {
            locale: dict(values)
            for locale, values in (working.get("translations") or {}).items()
        }
        for field in ("internal_name", "slug", "placement", "sort_order", "is_visible",
                      "media_id", "cta_url", "secondary_cta_url", "payload"):
            if field in data:
                value = data[field]
                if field in ("cta_url", "secondary_cta_url"):
                    value = cms.validate_url(value)
                working[field] = value
        if "slug" in data and not str(working.get("slug") or "").strip() and entry.content_type not in ("homepage_section", "department_visual"):
            working["slug"] = _generated_slug(
                entry.content_type, working.get("internal_name") or entry.internal_name
            )
        if translations is not None:
            for locale, values in translations.items():
                current = working["translations"].setdefault(locale, {})
                current.update(
                    values.model_dump(exclude_unset=True)
                    if hasattr(values, "model_dump") else values
                )
        _validate_content(entry.content_type, working.get("slug", ""),
                          working.get("translations", {}), working.get("cta_url"),
                          working.get("secondary_cta_url"), working.get("media_id"),
                          working.get("payload", {}))
        await _ensure_unique_slug(session, entry.content_type, working.get("slug", ""), entry.id)
        await _validate_references(
            session, entry.content_type, working.get("slug", ""),
            working.get("payload") or {}, working.get("media_id"),
        )
        if (
            entry.content_type == "footer_group"
            and working.get("slug") != entry.slug
            and await _footer_group_in_use(session, entry.slug)
        ):
            raise HTTPException(status_code=409, detail={"error": "footer_group_in_use"})
        entry.draft_snapshot = working
        await cms.add_revision(session, entry, "saved_draft", user.id, snapshot_override=working)
    else:
        _validate_content(entry.content_type, data.get("slug", entry.slug),
                          translations or {}, data.get("cta_url", entry.cta_url),
                          data.get("secondary_cta_url", entry.secondary_cta_url),
                          data.get("media_id", entry.media_id),
                          data.get("payload", entry.payload or {}))
        new_slug = data.get("slug", entry.slug)
        await _ensure_unique_slug(session, entry.content_type, new_slug, entry.id)
        await _validate_references(
            session, entry.content_type, new_slug,
            data.get("payload", entry.payload or {}), data.get("media_id", entry.media_id),
        )
        if (
            entry.content_type == "footer_group"
            and new_slug != entry.slug
            and await _footer_group_in_use(session, entry.slug)
        ):
            raise HTTPException(status_code=409, detail={"error": "footer_group_in_use"})
        for field in ("internal_name", "slug", "placement", "sort_order", "is_visible",
                      "media_id", "cta_url", "secondary_cta_url", "payload"):
            if field in data:
                value = data[field]
                if field in ("cta_url", "secondary_cta_url"):
                    value = cms.validate_url(value)
                setattr(entry, field, value)
        if "slug" in data and not str(entry.slug or "").strip() and entry.content_type not in ("homepage_section", "department_visual"):
            entry.slug = _generated_slug(entry.content_type, entry.internal_name)
        if translations is not None:
            await _upsert_translations(session, entry.id, translations)
        await cms.add_revision(session, entry, "saved_draft", user.id)
    entry.updated_by = user.id
    await cms.audit(session, user.id, "cms.content.update", entry.content_type, entry.id, None)
    await session.commit()
    return await cms.entry_detail(session, entry)


@router.post("/content/{entry_id}/status")
async def change_status(
    entry_id: str,
    payload: StatusIn,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    entry = await _get_entry(session, entry_id, lock=True)
    target = cms.status_transition_allowed(entry.status, payload.action)
    if not target:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_transition", "current": entry.status, "action": payload.action},
        )
    if payload.action == "publish":
        if entry.status == "published" and entry.draft_snapshot is None:
            raise HTTPException(status_code=409, detail={"error": "no_unpublished_changes"})
        snapshot = entry.draft_snapshot or await cms.snapshot_entry(session, entry)
        await _validate_publish(session, entry.content_type, snapshot, entry.id)
        if entry.draft_snapshot is not None:
            cms.apply_snapshot(entry, snapshot)
            await _replace_translations(session, entry.id, snapshot.get("translations") or {})
            entry.draft_snapshot = None
    entry.status = target
    entry.updated_by = user.id
    if target == "published":
        from datetime import datetime, timezone
        entry.published_at = datetime.now(timezone.utc)
    action_map = {"publish": "published", "unpublish": "unpublished", "archive": "archived"}
    await cms.add_revision(session, entry, action_map[payload.action], user.id)
    await cms.audit(session, user.id, f"cms.content.{payload.action}", entry.content_type, entry.id, None)
    await session.commit()
    return await cms.entry_detail(session, entry)


@router.post("/content/{entry_id}/preview-token")
async def make_preview(
    entry_id: str,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    entry = await _get_entry(session, entry_id)
    token = cms.make_preview_token(entry.id)
    return {
        "preview_url": f"/api/v1/cms/preview/{token}",
        "preview_page_url": f"/preview/{token}",
        "expires_in": 3600,
    }


@router.get("/content/{entry_id}/revisions")
async def list_revisions(
    entry_id: str,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    await _get_entry(session, entry_id)
    rows = (
        await session.execute(
            select(CmsRevision)
            .where(CmsRevision.content_id == entry_id)
            .order_by(CmsRevision.version_number.desc())
        )
    ).scalars().all()
    return [
        {
            "id": r.id,
            "version_number": r.version_number,
            "action": r.action,
            "created_by": r.created_by,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.post("/content/{entry_id}/restore/{revision_id}")
async def restore_revision(
    entry_id: str,
    revision_id: str,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    entry = await _get_entry(session, entry_id, lock=True)
    revision = await session.scalar(
        select(CmsRevision).where(
            CmsRevision.id == revision_id, CmsRevision.content_id == entry_id
        )
    )
    if not revision or not revision.snapshot:
        raise HTTPException(status_code=404, detail="revision_not_found")
    snap = revision.snapshot
    _validate_content(entry.content_type, snap.get("slug", ""), snap.get("translations", {}),
                      snap.get("cta_url"), snap.get("secondary_cta_url"),
                      snap.get("media_id"), snap.get("payload", {}))
    await _ensure_unique_slug(session, entry.content_type, snap.get("slug", ""), entry.id)
    await _validate_references(session, entry.content_type, snap.get("slug", ""),
                               snap.get("payload", {}), snap.get("media_id"))
    if entry.status in ("published", "archived"):
        entry.draft_snapshot = snap
    else:
        cms.apply_snapshot(entry, snap)
        await _replace_translations(session, entry.id, snap.get("translations", {}))
        entry.draft_snapshot = None
    entry.updated_by = user.id
    await cms.add_revision(
        session, entry, "restored", user.id,
        snapshot_override=snap if entry.draft_snapshot is not None else None,
    )
    await cms.audit(session, user.id, "cms.content.restore", entry.content_type, entry.id,
                    {"from_version": revision.version_number})
    await session.commit()
    return await cms.entry_detail(session, entry)


@router.delete("/content/{entry_id}", status_code=204)
async def delete_content(
    entry_id: str,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    entry = await _get_entry(session, entry_id, lock=True)
    if entry.status != "archived":
        raise HTTPException(status_code=409, detail={"error": "content_must_be_archived"})
    if entry.content_type == "footer_group":
        if await _footer_group_in_use(session, entry.slug):
            raise HTTPException(status_code=409, detail={"error": "footer_group_in_use"})
    await session.execute(
        delete(CmsContentTranslation).where(CmsContentTranslation.entry_id == entry.id)
    )
    await session.execute(delete(CmsRevision).where(CmsRevision.content_id == entry.id))
    await cms.audit(
        session, user.id, "cms.content.delete", entry.content_type, entry.id,
        {"name": entry.internal_name, "slug": entry.slug},
    )
    await session.delete(entry)
    await session.commit()
    return None


# ------------------------------ media -------------------------------------


def _sniff(data: bytes) -> Optional[str]:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@router.post("/media", status_code=201)
async def upload_media(
    file: UploadFile,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    chunks = []
    size = 0
    while True:
        chunk = await file.read(min(64 * 1024, MAX_UPLOAD_BYTES + 1 - size))
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
        if size > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail={"error": "file_too_large", "max_bytes": MAX_UPLOAD_BYTES},
            )
    data = b"".join(chunks)
    if not data:
        raise HTTPException(status_code=400, detail={"error": "empty_file"})
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail={"error": "file_too_large", "max_bytes": MAX_UPLOAD_BYTES})
    declared = (file.content_type or "").lower()
    # Browsers normally report JPEG as image/jpeg, but some local file
    # providers report image/jpg or omit the type. The file signature remains
    # authoritative; normalize the declaration before validating it.
    if declared == "image/jpg":
        declared = "image/jpeg"
    sniffed = _sniff(data)
    if sniffed is None:
        raise HTTPException(status_code=415, detail={"error": "unsupported_media_type"})
    if declared and declared not in ALLOWED_MIME:
        raise HTTPException(status_code=415, detail={"error": "unsupported_media_type"})
    if declared and sniffed != declared:
        raise HTTPException(status_code=415, detail={"error": "content_mismatch"})
    declared = sniffed
    width = height = None
    try:
        import io
        from PIL import Image

        with Image.open(io.BytesIO(data)) as img:
            img.verify()
            width, height = img.size
    except ImportError:
        pass  # dimensions optional; magic bytes already validated
    except Exception:
        raise HTTPException(status_code=415, detail={"error": "invalid_image"})

    checksum = hashlib.sha256(data).hexdigest()
    # ``checksum`` is the idempotency key for generated/imported assets. The
    # schema keeps it nullable-compatible for older installations, so use a
    # transaction advisory lock to serialize concurrent first uploads without
    # changing existing CMS data or requiring a destructive migration.
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(checksum)))
    )
    existing = await session.scalar(
        select(CmsMediaAsset).where(CmsMediaAsset.checksum == checksum)
    )
    if existing:
        # Checksum makes retries/resumable imports idempotent and avoids
        # creating duplicate library entries for the same generated asset.
        return await _media_payload(session, existing)

    key = f"{uuid.uuid4().hex}{ALLOWED_MIME[declared]}"
    storage = get_media_storage()
    await storage.save(data, key, declared)
    asset = CmsMediaAsset(
        storage_provider=storage.name,
        storage_key=key,
        original_filename=(file.filename or "")[:255],
        mime_type=declared,
        file_size=len(data),
        width=width,
        height=height,
        checksum=checksum,
        created_by=user.id,
    )
    try:
        session.add(asset)
        await session.flush()
        await cms.audit(session, user.id, "cms.media.upload", "media", asset.id,
                        {"filename": asset.original_filename, "size": asset.file_size})
        await session.commit()
    except Exception:
        await session.rollback()
        try:
            await storage.delete(key)
        except Exception:
            pass
        raise
    return await _media_payload(session, asset)


async def _media_payload(session: AsyncSession, asset: CmsMediaAsset) -> dict:
    translations = (
        await session.execute(
            select(CmsMediaTranslation).where(CmsMediaTranslation.media_id == asset.id)
        )
    ).scalars().all()
    usage_items = await _media_usage_details(session, asset)
    return {
        "id": asset.id,
        "url": await cms.media_url(session, asset),
        "original_filename": asset.original_filename,
        "mime_type": asset.mime_type,
        "file_size": asset.file_size,
        "width": asset.width,
        "height": asset.height,
        "checksum": asset.checksum,
        "created_at": asset.created_at,
        "usage_count": len(usage_items),
        "usage": usage_items,
        "translations": {
            t.locale: {"alt_text": t.alt_text, "caption": t.caption} for t in translations
        },
    }


def _product_media_item_matches(item: object, asset: CmsMediaAsset) -> bool:
    if isinstance(item, dict) and item.get("media_id") == asset.id:
        return True
    url = media_item_url(item)
    if not isinstance(url, str):
        return False
    return url.split("?", 1)[0].rstrip("/").endswith(
        f"/api/v1/cms/media/file/{asset.storage_key}"
    )


async def _media_usage_count(session: AsyncSession, asset: CmsMediaAsset) -> int:
    return len(await _media_usage_details(session, asset))


async def _media_usage_details(session: AsyncSession, asset: CmsMediaAsset) -> list[dict]:
    usages: list[dict] = []
    content_rows = (
        await session.execute(
            select(CmsContentEntry).where(CmsContentEntry.media_id == asset.id)
        )
    ).scalars().all()
    usages.extend(
        {
            "type": "cms",
            "id": entry.id,
            "label": entry.internal_name or entry.slug,
            "href": f"/admin/cms/{entry.id}",
        }
        for entry in content_rows
    )
    staged_rows = (
        await session.execute(
            select(CmsContentEntry).where(CmsContentEntry.draft_snapshot.is_not(None))
        )
    ).scalars().all()
    usages.extend(
        {
            "type": "cms-draft",
            "id": entry.id,
            "label": entry.internal_name or entry.slug,
            "href": f"/admin/cms/{entry.id}",
        }
        for entry in staged_rows
        if (entry.draft_snapshot or {}).get("media_id") == asset.id
    )

    category_rows = (
        await session.execute(select(Category).where(Category.media_id == asset.id))
    ).scalars().all()
    usages.extend(
        {
            "type": category.kind,
            "id": category.id,
            "label": category.slug,
            "href": "/admin/categories",
        }
        for category in category_rows
    )

    variant_rows = (
        await session.execute(
            select(ProductVariant, Product)
            .join(Product, ProductVariant.product_id == Product.id)
            .where(ProductVariant.media_id == asset.id)
        )
    ).all()
    usages.extend(
        {
            "type": "variant",
            "id": variant.id,
            "label": f"{product.slug} · {variant.sku}",
            "href": f"/admin/products/{product.id}",
        }
        for variant, product in variant_rows
    )

    product_media = (
        await session.execute(select(Product.id, Product.slug, Product.media))
    ).all()
    for product_id, product_slug, media in product_media:
        if any(_product_media_item_matches(item, asset) for item in (media or [])):
            usages.append(
                {
                    "type": "product",
                    "id": product_id,
                    "label": product_slug,
                    "href": f"/admin/products/{product_id}",
                }
            )
    return usages


@router.get("/media")
async def list_media(
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    q: Optional[str] = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=48, ge=1, le=100),
):
    query = select(CmsMediaAsset)
    count_q = select(func.count(CmsMediaAsset.id))
    if q:
        query = query.where(CmsMediaAsset.original_filename.ilike(f"%{q}%"))
        count_q = count_q.where(CmsMediaAsset.original_filename.ilike(f"%{q}%"))
    total = await session.scalar(count_q)
    rows = (
        await session.execute(
            query.order_by(CmsMediaAsset.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return {
        "items": [await _media_payload(session, r) for r in rows],
        "total": int(total or 0),
        "page": page,
        "page_size": page_size,
    }


@router.patch("/media/{media_id}")
async def update_media(
    media_id: str,
    payload: MediaPatchIn,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    asset = await session.scalar(
        select(CmsMediaAsset).where(CmsMediaAsset.id == media_id).with_for_update()
    )
    if not asset:
        raise HTTPException(status_code=404, detail="media_not_found")
    unknown = set(payload.translations) - set(cms.LOCALES)
    if unknown:
        raise HTTPException(status_code=400, detail={"error": "invalid_locale"})
    existing = {
        t.locale: t
        for t in (
            await session.execute(
                select(CmsMediaTranslation).where(CmsMediaTranslation.media_id == asset.id)
            )
        ).scalars().all()
    }
    for locale, values in payload.translations.items():
        values = values.model_dump(exclude_unset=True)
        alt = cms.sanitize_text(values["alt_text"], 255) if "alt_text" in values else None
        caption = cms.sanitize_text(values["caption"], 500) if "caption" in values else None
        if locale in existing:
            if alt is not None:
                existing[locale].alt_text = alt
            if caption is not None:
                existing[locale].caption = caption
        else:
            session.add(CmsMediaTranslation(media_id=asset.id, locale=locale,
                                            alt_text=alt or "", caption=caption or ""))
    await cms.audit(
        session, user.id, "cms.media.update", "media", asset.id,
        {"filename": asset.original_filename},
    )
    await session.commit()
    return await _media_payload(session, asset)


@router.delete("/media/{media_id}")
async def delete_media(
    media_id: str,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    asset = await session.scalar(
        select(CmsMediaAsset).where(CmsMediaAsset.id == media_id).with_for_update()
    )
    if not asset:
        raise HTTPException(status_code=404, detail="media_not_found")
    usage = await _media_usage_count(session, asset)
    if usage:
        raise HTTPException(
            status_code=409,
            detail={"error": "media_in_use", "usage_count": int(usage)},
        )
    storage = get_media_storage()
    storage_key = asset.storage_key
    filename = asset.original_filename
    await cms.audit(session, user.id, "cms.media.delete", "media", asset.id,
                    {"filename": filename})
    await session.delete(asset)
    await session.commit()
    try:
        await storage.delete(storage_key)
        return {"deleted": True}
    except Exception:
        return {"deleted": True, "storage_cleanup_pending": True}
