"""Redis-backed task queue.

A deliberately simple list-based queue for Sprint 1: ``enqueue`` right-pushes a
``task_id`` and the worker left-pops it (FIFO). This is enough to demonstrate the
QUEUED -> RUNNING -> COMPLETED lifecycle and can be replaced by a richer
priority/stream implementation later without changing callers.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable
from typing import cast

from app import redis_client
from app.core.config import get_settings

# redis-py types its command methods as ``Awaitable[T] | T`` (shared sync/async
# base class); on an async client they always return awaitables, so we cast.


async def enqueue(task_id: str) -> None:
    """Append a task id to the work queue."""

    settings = get_settings()
    redis = redis_client.get_redis()
    await cast(Awaitable[int], redis.rpush(settings.task_queue_key, task_id))


async def dequeue(timeout: int | None = None) -> str | None:
    """Block until a task id is available or the timeout elapses.

    Returns ``None`` on timeout so the worker loop can check for shutdown.
    """

    settings = get_settings()
    redis = redis_client.get_redis()
    result = await cast(
        Awaitable[tuple[str, str] | None],
        redis.blpop(
            [settings.task_queue_key],
            timeout=settings.worker_poll_timeout if timeout is None else timeout,
        ),
    )
    if result is None:
        return None
    # result is (queue_key, value); decode_responses=True gives str.
    return result[1]


async def queue_depth() -> int:
    settings = get_settings()
    redis = redis_client.get_redis()
    return int(await cast(Awaitable[int], redis.llen(settings.task_queue_key)))


async def enqueue_delayed(task_id: str, delay: float) -> None:
    """Schedule a task to become ready after ``delay`` seconds (retry/backoff).

    Backed by a Redis sorted set scored by the ready-at timestamp; the scheduler
    promotes due entries into the main queue.
    """

    settings = get_settings()
    redis = redis_client.get_redis()
    ready_at = time.time() + max(0.0, delay)
    await cast(Awaitable[int], redis.zadd(settings.delayed_queue_key, {task_id: ready_at}))


async def promote_due(now: float | None = None) -> int:
    """Move all due delayed tasks into the main queue. Returns how many moved."""

    settings = get_settings()
    redis = redis_client.get_redis()
    cutoff = time.time() if now is None else now
    due = await cast(
        Awaitable[list[str]],
        redis.zrangebyscore(settings.delayed_queue_key, "-inf", cutoff),
    )
    moved = 0
    for task_id in due:
        # ZREM acts as the claim: only the caller that removes it enqueues it.
        removed = int(
            await cast(Awaitable[int], redis.zrem(settings.delayed_queue_key, task_id))
        )
        if removed:
            await cast(Awaitable[int], redis.rpush(settings.task_queue_key, task_id))
            moved += 1
    return moved


async def delayed_depth() -> int:
    settings = get_settings()
    redis = redis_client.get_redis()
    return int(await cast(Awaitable[int], redis.zcard(settings.delayed_queue_key)))
