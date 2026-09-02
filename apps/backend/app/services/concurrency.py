"""Redis-backed concurrency limiter (spec §7).

Enforces limits across several scopes at once (global / per-user / per-type).
``acquire`` increments all requested counters and, if any exceeds its limit,
rolls them all back and returns ``None`` (nothing acquired). ``release`` gives
the slots back. Scopes with a limit of 0 are treated as unlimited and skipped.

Note: acquire is not fully atomic across keys (no Lua) — a small race window
exists under heavy contention, which is acceptable for Sprint-scope scheduling
and keeps it compatible with the in-memory fake used by the test suite.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import cast

from app import redis_client

_PREFIX = "atlas:concurrency:"


def build_scopes(
    *, owner_id: str | None, task_type: str, limits: dict[str, int]
) -> dict[str, int]:
    """Map limit config to concrete Redis keys with their limits."""

    scopes: dict[str, int] = {}
    if limits.get("global", 0) > 0:
        scopes[f"{_PREFIX}global"] = limits["global"]
    if limits.get("per_user", 0) > 0 and owner_id:
        scopes[f"{_PREFIX}user:{owner_id}"] = limits["per_user"]
    if limits.get("per_type", 0) > 0 and task_type:
        scopes[f"{_PREFIX}type:{task_type}"] = limits["per_type"]
    return scopes


async def acquire(scopes: dict[str, int]) -> list[str] | None:
    """Try to reserve one slot in every scope. Returns keys to release, or None."""

    if not scopes:
        return []
    redis = redis_client.get_redis()
    acquired: list[str] = []
    for key, limit in scopes.items():
        value = int(await cast(Awaitable[int], redis.incr(key)))
        acquired.append(key)
        if value > limit:
            await release(acquired)
            return None
    return acquired


async def release(keys: list[str]) -> None:
    redis = redis_client.get_redis()
    for key in keys:
        # Never let a counter go negative.
        value = int(await cast(Awaitable[int], redis.decr(key)))
        if value < 0:
            await cast(Awaitable[int], redis.set(key, 0))
