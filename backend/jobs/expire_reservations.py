"""Reservation expiry sweep — standard VPS scheduler entry point.

The lazy in-request sweep remains for development. On the VPS, run this
from cron or a systemd timer, e.g. every minute:

    * * * * * cd /app/backend && /path/to/venv/bin/python -m jobs.expire_reservations

No platform-specific scheduler dependency.
"""

import asyncio
import logging

from checkout.service import expire_due_reservations
from db.session import SessionLocal

logger = logging.getLogger("jobs.expire_reservations")


async def main() -> None:
    async with SessionLocal() as session:
        await expire_due_reservations(session)
        await session.commit()
    logger.info("reservation expiry sweep complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
