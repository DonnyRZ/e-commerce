"""Remove media assets that are no longer referenced by CMS content or products.

Run from the backend directory with a conservative retention window:

    python -m jobs.cleanup_orphan_media --older-than-days 7

Use ``--dry-run`` before enabling the scheduled job in production.
"""

import argparse
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from db.models import Category, CmsContentEntry, CmsMediaAsset, Product, ProductVariant
from db.session import SessionLocal
from storage import get_media_storage

logger = logging.getLogger("jobs.cleanup_orphan_media")


async def cleanup(*, older_than_days: int = 7, dry_run: bool = False) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    storage = get_media_storage()
    async with SessionLocal() as session:
        assets = (
            await session.execute(
                select(CmsMediaAsset).where(CmsMediaAsset.created_at < cutoff)
            )
        ).scalars().all()
        content_refs = set(
            (
                await session.execute(
                    select(CmsContentEntry.media_id).where(CmsContentEntry.media_id.is_not(None))
                )
            ).scalars().all()
        )
        category_refs = set(
            (
                await session.execute(
                    select(Category.media_id).where(Category.media_id.is_not(None))
                )
            ).scalars().all()
        )
        variant_refs = set(
            (
                await session.execute(
                    select(ProductVariant.media_id).where(ProductVariant.media_id.is_not(None))
                )
            ).scalars().all()
        )
        product_media = (await session.execute(select(Product.media))).scalars().all()

        def referenced_by_product(asset):
            suffix = f"/api/v1/cms/media/file/{asset.storage_key}"
            return any(
                isinstance(item, dict)
                and (
                    item.get("media_id") == asset.id
                    or (
                        isinstance(item.get("url"), str)
                        and item["url"].split("?", 1)[0].rstrip("/").endswith(suffix)
                    )
                )
                for media in product_media
                for item in (media or [])
            )

        rows = [
            asset
            for asset in assets
            if (
                asset.id not in content_refs
                and asset.id not in category_refs
                and asset.id not in variant_refs
                and not referenced_by_product(asset)
            )
        ]
        for asset in rows:
            logger.info("orphan media candidate id=%s key=%s", asset.id, asset.storage_key)
            if dry_run:
                continue
            await storage.delete(asset.storage_key)
            await session.delete(asset)
        if not dry_run:
            await session.commit()
        return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--older-than-days", type=int, default=7)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    count = asyncio.run(
        cleanup(older_than_days=max(args.older_than_days, 1), dry_run=args.dry_run)
    )
    logger.info("orphan media scan complete: %s candidate(s)", count)
