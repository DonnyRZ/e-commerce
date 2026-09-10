"""Remove CMS media assets that are no longer referenced by published/draft content.

Run from the backend directory with a conservative retention window:

    python -m jobs.cleanup_orphan_media --older-than-days 7

Use ``--dry-run`` before enabling the scheduled job in production.
"""

import argparse
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from db.models import CmsContentEntry, CmsMediaAsset
from db.session import SessionLocal
from storage import get_media_storage

logger = logging.getLogger("jobs.cleanup_orphan_media")


async def cleanup(*, older_than_days: int = 7, dry_run: bool = False) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    storage = get_media_storage()
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(CmsMediaAsset)
                .outerjoin(
                    CmsContentEntry,
                    CmsContentEntry.media_id == CmsMediaAsset.id,
                )
                .where(
                    CmsContentEntry.id.is_(None),
                    CmsMediaAsset.created_at < cutoff,
                )
            )
        ).scalars().all()
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

