"""Redis-backed task queue.

A deliberately simple list-based queue for Sprint 1: ``enqueue`` right-pushes a
``task_id`` and the worker left-pops it (FIFO). This is enough to demonstrate the
QUEUED -> RUNNING -> COMPLETED lifecycle and can be replaced by a richer
priority/stream implementation later without changing callers.
"""

from __future__ import annotations

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
