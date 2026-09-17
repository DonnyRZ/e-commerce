"""Public CMS API — published content only (drafts never leak), plus
HMAC-signed time-limited draft preview and media file serving."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from cms import service as cms
from db.models import Category, CmsContentEntry, CmsMediaAsset
from db.session import get_session
from storage import get_media_storage

router = APIRouter(prefix="/api/v1/cms", tags=["cms"])


async def _published(session: AsyncSession, content_type: str) -> list:
    rows = (
        await session.execute(
            select(CmsContentEntry)
            .where(
                CmsContentEntry.content_type == content_type,
                CmsContentEntry.status == "published",
                CmsContentEntry.is_visible == True
            )
            .order_by(CmsContentEntry.sort_order, CmsContentEntry.created_at)
        )
    ).scalars().all()
    return [await cms.public_entry(session, r) for r in rows]


@router.get("/public/bundle")
async def public_bundle(session: AsyncSession = Depends(get_session)):
    sections = await _published(session, "homepage_section")
    heroes = await _published(session, "hero")
    announcements = await _published(session, "announcement")
    footer_texts = await _published(session, "footer_text")
    return {
        "sections": [
            {"key": s["slug"], "sort_order": s["sort_order"]} for s in sections
        ],
        "hero": heroes[0] if heroes else None,
        "announcement": announcements[0] if announcements else None,
        "stories": await _published(session, "story"),
        "story_title": next((item for item in footer_texts if item["placement"] == "home_stories"), None),
        "banners": await _published(session, "banner"),
        "department_visuals": await _published(session, "department_visual"),
    }


@router.get("/public/footer")
async def public_footer(session: AsyncSession = Depends(get_session)):
    groups = await _published(session, "footer_group")
    items = await _published(session, "footer_item")
    texts = await _published(session, "footer_text")
    out_groups = []
    for g in groups:
        g_items = [
            i for i in items if (i["payload"] or {}).get("group") == g["slug"]
        ]
        out_groups.append({**g, "items": g_items})

    # Catalog departments are data, not CMS copy.  Keep the CMS-managed shop
    # links (new/sale/etc.) while replacing any stale hardcoded department
    # links with the current active taxonomy roots.
    departments = (
        await session.execute(
            select(Category)
            .options(selectinload(Category.translations))
            .where(
                Category.kind == "department",
                Category.department == Category.slug,
                Category.parent_id.is_(None),
                Category.is_active.is_(True),
            )
            .order_by(Category.sort_order, Category.slug)
        )
    ).scalars().all()
    catalog_items = [
        {
            "id": f"catalog-{department.id}",
            "content_type": "footer_item",
            "slug": f"catalog-{department.slug}",
            "placement": "footer",
            "sort_order": index + 2,
            "image_url": None,
            "cta_url": f"/shop?department={department.slug}",
            "secondary_cta_url": None,
            "payload": {"group": "shop", "source": "catalog"},
            "translations": {
                translation.locale: {"title": translation.name}
                for translation in department.translations
            },
        }
        for index, department in enumerate(departments)
    ]
    for group in out_groups:
        if group["slug"] != "shop":
            continue
        group["items"] = [
            item
            for item in group["items"]
            if not (item.get("cta_url") or "").startswith("/shop?department=")
        ] + catalog_items
        break
    return {
        "groups": out_groups,
        "promo": next((item for item in texts if item["placement"] == "footer"), None),
    }


@router.get("/public/navigation")
async def public_navigation(session: AsyncSession = Depends(get_session)):
    return {"items": await _published(session, "nav_item")}


@router.get("/public/pages/{slug}")
async def public_page(slug: str, session: AsyncSession = Depends(get_session)):
    entry = await session.scalar(
        select(CmsContentEntry).where(
            CmsContentEntry.content_type == "page",
            CmsContentEntry.slug == slug,
            CmsContentEntry.status == "published",
            CmsContentEntry.is_visible == True,
        )
    )
    if not entry:
        raise HTTPException(status_code=404, detail="page_not_found")
    return await cms.public_entry(session, entry)


@router.get("/public/faq")
async def public_faq(session: AsyncSession = Depends(get_session)):
    return {"items": await _published(session, "faq_item")}


@router.get("/preview/{token}")
async def preview_entry(
    token: str,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    entry_id = cms.verify_preview_token(token)
    entry = await session.get(CmsContentEntry, entry_id) if entry_id else None
    if not entry:
        raise HTTPException(status_code=404, detail="preview_not_found")
    result = await cms.public_entry(session, entry, use_working_copy=True)
    result["internal_name"] = (entry.draft_snapshot or {}).get("internal_name", entry.internal_name)
    return result


@router.get("/media/file/{key}")
async def media_file(key: str, session: AsyncSession = Depends(get_session)):
    asset = await session.scalar(
        select(CmsMediaAsset).where(CmsMediaAsset.storage_key == key)
    )
    if not asset:
        raise HTTPException(status_code=404, detail="media_not_found")
    storage = get_media_storage()
    public_url = storage.public_url(asset.storage_key)
    if public_url:
        return RedirectResponse(
            public_url,
            headers={
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "public, max-age=31536000, immutable",
            },
        )
    file_path = storage.resolve_path(asset.storage_key)
    if not Path(file_path).is_file():
        # A DB row can outlive a manually removed local file. Return a stable
        # 404 instead of turning a missing asset into a framework 500.
        raise HTTPException(status_code=404, detail="media_not_found")
    return FileResponse(
        file_path,
        media_type=asset.mime_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )
