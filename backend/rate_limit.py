"""Process-shared rate limiting primitives.

Development and test can use the small in-process limiter in the routers. Any
staging/production deployment must select Redis so multiple API workers share
the same counters and an individual worker restart cannot reset protection.
"""

from __future__ import annotations

from fastapi import HTTPException
from redis.asyncio import Redis

from config import REDIS_URL

_redis: Redis | None = None


def _client() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(REDIS_URL, decode_responses=True)
    return _redis


async def enforce_redis_limit(
    scope: str, identity: str, *, limit: int, window_seconds: int
) -> None:
    """Increment a fixed-window counter or raise a safe, explicit error."""

    key = f"muslimah-cantik:rate:{scope}:{identity}"
    try:
        client = _client()
        async with client.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, window_seconds)
            count, _ = await pipe.execute()
    except Exception as exc:
        # Failing closed avoids silently losing protection when Redis is down.
        raise HTTPException(status_code=503, detail="rate_limit_unavailable") from exc
    if int(count) > limit:
        raise HTTPException(status_code=429, detail="too_many_requests")


async def check_redis_health() -> None:
    await _client().ping()


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
