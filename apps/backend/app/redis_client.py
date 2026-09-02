"""Redis client accessor.

Centralised so tests can swap in an in-memory fake by overriding
:func:`get_redis`. Always call ``redis_client.get_redis()`` at call time (never
cache the return value at import) so overrides take effect.
"""

from __future__ import annotations

from functools import lru_cache

import redis.asyncio as redis

from app.core.config import get_settings


@lru_cache
def get_redis() -> redis.Redis:
    """Return a cached async Redis client built from settings."""

    settings = get_settings()
    return redis.from_url(settings.redis_url, decode_responses=True)
