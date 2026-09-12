"""CMS admin API — content CRUD, draft/publish/archive, preview tokens,
revisions, media library. Admin role only; CSRF on mutations; all text
sanitized and URLs validated; mass-assignment safe (status/workflow fields
are never settable through the content payload).
"""

import hashlib
import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import csrf_protect, require_roles
from cms import service as cms
from db.models import (
    CmsContentEntry,
    CmsContentTranslation,
    CmsMediaAsset,
    CmsMediaTranslation,
    CmsRevision,
    Product,
    User,
)
from db.session import get_session
from storage import get_media_storage

router = APIRouter(prefix="/api/v1/admin/cms", tags=["admin-cms"])

require_admin = require_roles("admin")

_SLUG = re.compile(r"^[a-z0-9][a-z0-9\-]{0,158}$")

ALLOWED_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


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


class MediaPatchIn(BaseModel):
    translations: dict[str, dict] = Field(default_factory=dict)  # locale -> {alt_text, caption}


def _validate_content(content_type: str, slug: str, translations: dict,
                      cta_url: Optional[str], secondary_cta_url: Optional[str],
                      media_id: Optional[str]) -> None:
    if content_type not in cms.CONTENT_TYPES:
        raise HTTPException(status_code=400, detail={"error": "invalid_content_type"})
    if slug and not _SLUG.match(slug):
        raise HTTPException(status_code=400, detail={"error": "invalid_slug"})
    unknown = set(translations) - set(cms.LOCALES)
    if unknown:
        raise HTTPException(status_code=400, detail={"error": "invalid_locale", "locales": sorted(unknown)})
    try:
        cms.validate_url(cta_url)
        cms.validate_url(secondary_cta_url)
        for tr in translations.values():
            values = tr if isinstance(tr, dict) else tr.model_dump()
            for value in values.values():
                cms.sanitize_text(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)})
    if media_id is not None and len(media_id) > 40:
        raise HTTPException(status_code=400, detail={"error": "invalid_media"})


async def _get_entry(session: AsyncSession, entry_id: str) -> CmsContentEntry:
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
        values = tr.model_dump() if hasattr(tr, "model_dump") else tr
        if locale in existing:
            row = existing[locale]
            for key, value in values.items():
                setattr(row, key, value)
        else:
            session.add(CmsContentTranslation(entry_id=entry_id, locale=locale, **values))


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
                      payload.cta_url, payload.secondary_cta_url, payload.media_id)
    if payload.media_id:
        if not await session.get(CmsMediaAsset, payload.media_id):
            raise HTTPException(status_code=400, detail={"error": "invalid_media"})
    entry = CmsContentEntry(
        content_type=payload.content_type,
        internal_name=payload.internal_name,
        slug=payload.slug or re.sub(r"[^a-z0-9]+", "-", payload.internal_name.lower()).strip("-")[:80],
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
    entry = await _get_entry(session, entry_id)
    data = payload.model_dump(exclude_unset=True)
    translations = data.pop("translations", None)
    _validate_content(entry.content_type, data.get("slug", entry.slug),
                      translations or {}, data.get("cta_url", entry.cta_url),
                      data.get("secondary_cta_url", entry.secondary_cta_url),
                      data.get("media_id", entry.media_id))
    if data.get("media_id"):
        if not await session.get(CmsMediaAsset, data["media_id"]):
            raise HTTPException(status_code=400, detail={"error": "invalid_media"})
    for field in ("internal_name", "slug", "placement", "sort_order", "is_visible",
                  "media_id", "cta_url", "secondary_cta_url", "payload"):
        if field in data:
            value = data[field]
            if field in ("cta_url", "secondary_cta_url"):
                value = cms.validate_url(value)
            setattr(entry, field, value)
    entry.updated_by = user.id
    if translations:
        await _upsert_translations(session, entry.id, translations)
    await cms.add_revision(session, entry, "saved_draft", user.id)
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
    entry = await _get_entry(session, entry_id)
    target = cms.status_transition_allowed(entry.status, payload.action)
    if not target:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_transition", "current": entry.status, "action": payload.action},
        )
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
    return {"preview_url": f"/api/v1/cms/preview/{token}", "expires_in": 3600}


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
    entry = await _get_entry(session, entry_id)
    revision = await session.scalar(
        select(CmsRevision).where(
            CmsRevision.id == revision_id, CmsRevision.content_id == entry_id
        )
    )
    if not revision or not revision.snapshot:
        raise HTTPException(status_code=404, detail="revision_not_found")
    snap = revision.snapshot
    entry.internal_name = snap.get("internal_name", entry.internal_name)
    entry.slug = snap.get("slug", entry.slug)
    entry.placement = snap.get("placement", entry.placement)
    entry.sort_order = snap.get("sort_order", entry.sort_order)
    entry.is_visible = snap.get("is_visible", entry.is_visible)
    entry.media_id = snap.get("media_id")
    entry.cta_url = snap.get("cta_url")
    entry.secondary_cta_url = snap.get("secondary_cta_url")
    entry.payload = snap.get("payload") or {}
    entry.status = "draft"  # restore always creates a new Draft
    entry.updated_by = user.id
    await _upsert_translations(session, entry.id, snap.get("translations", {}))
    await cms.add_revision(session, entry, "restored", user.id)
    await cms.audit(session, user.id, "cms.content.restore", entry.content_type, entry.id,
                    {"from_version": revision.version_number})
    await session.commit()
    return await cms.entry_detail(session, entry)


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
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail={"error": "empty_file"})
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail={"error": "file_too_large", "max_bytes": MAX_UPLOAD_BYTES})
    declared = (file.content_type or "").lower()
    if declared not in ALLOWED_MIME:
        raise HTTPException(status_code=415, detail={"error": "unsupported_media_type"})
    sniffed = _sniff(data)
    if sniffed != declared:
        raise HTTPException(status_code=415, detail={"error": "content_mismatch"})
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
        checksum=hashlib.sha256(data).hexdigest(),
        created_by=user.id,
    )
    session.add(asset)
    await session.flush()
    await cms.audit(session, user.id, "cms.media.upload", "media", asset.id,
                    {"filename": asset.original_filename, "size": asset.file_size})
    await session.commit()
    return await _media_payload(session, asset)


async def _media_payload(session: AsyncSession, asset: CmsMediaAsset) -> dict:
    translations = (
        await session.execute(
            select(CmsMediaTranslation).where(CmsMediaTranslation.media_id == asset.id)
        )
    ).scalars().all()
    usage = await _media_usage_count(session, asset)
    return {
        "id": asset.id,
        "url": await cms.media_url(session, asset),
        "original_filename": asset.original_filename,
        "mime_type": asset.mime_type,
        "file_size": asset.file_size,
        "width": asset.width,
        "height": asset.height,
        "created_at": asset.created_at,
        "usage_count": int(usage or 0),
        "translations": {
            t.locale: {"alt_text": t.alt_text, "caption": t.caption} for t in translations
        },
    }


def _product_media_item_matches(item: object, asset: CmsMediaAsset) -> bool:
    if not isinstance(item, dict):
        return False
    if item.get("media_id") == asset.id:
        return True
    url = item.get("url")
    if not isinstance(url, str):
        return False
    return url.split("?", 1)[0].rstrip("/").endswith(
        f"/api/v1/cms/media/file/{asset.storage_key}"
    )


async def _media_usage_count(session: AsyncSession, asset: CmsMediaAsset) -> int:
    content_usage = await session.scalar(
        select(func.count(CmsContentEntry.id)).where(CmsContentEntry.media_id == asset.id)
    )
    product_media = (
        await session.execute(select(Product.media))
    ).scalars().all()
    product_usage = sum(
        1
        for media in product_media
        for item in (media or [])
        if _product_media_item_matches(item, asset)
    )
    return int(content_usage or 0) + product_usage


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
    asset = await session.get(CmsMediaAsset, media_id)
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
        alt = cms.sanitize_text(values.get("alt_text", ""), 255)
        caption = cms.sanitize_text(values.get("caption", ""), 500)
        if locale in existing:
            existing[locale].alt_text = alt
            existing[locale].caption = caption
        else:
            session.add(CmsMediaTranslation(media_id=asset.id, locale=locale,
                                            alt_text=alt, caption=caption))
    await session.commit()
    return await _media_payload(session, asset)


@router.delete("/media/{media_id}")
async def delete_media(
    media_id: str,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(csrf_protect),
):
    asset = await session.get(CmsMediaAsset, media_id)
    if not asset:
        raise HTTPException(status_code=404, detail="media_not_found")
    usage = await _media_usage_count(session, asset)
    if usage:
        raise HTTPException(
            status_code=409,
            detail={"error": "media_in_use", "usage_count": int(usage)},
        )
    storage = get_media_storage()
    await storage.delete(asset.storage_key)
    await cms.audit(session, user.id, "cms.media.delete", "media", asset.id,
                    {"filename": asset.original_filename})
    await session.delete(asset)
    await session.commit()
    return {"deleted": True}
