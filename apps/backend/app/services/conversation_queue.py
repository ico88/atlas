"""Per-conversation message queue (ROADMAP PR 11).

Semantics:

- **immediate send** — a message to an idle conversation is dispatched at once;
- **queueing**       — a message to a busy conversation waits in a FIFO queue;
- **merge**          — consecutive *pending* user messages are coalesced into one
  so rapid-fire turns don't pile up;
- **parallelism**    — each conversation runs one turn at a time (a per-conversation
  lock), while up to ``conversation_max_parallel`` different conversations run
  concurrently.

State lives in Redis so it is shared across worker processes and survives a
restart. Following ``services/concurrency.py``, operations are pragmatically
atomic (no Lua) — acceptable for sprint-scope scheduling and compatible with the
in-memory fake used by the test suite.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable
from typing import Any, cast

from app import redis_client
from app.core.config import get_settings
from app.models.base import new_uuid

logger = logging.getLogger(__name__)

_PREFIX = "atlas:convq:"
_ACTIVE_COUNT = f"{_PREFIX}active_count"


def _pending_key(cid: str) -> str:
    return f"{_PREFIX}pending:{cid}"


def _active_key(cid: str) -> str:
    return f"{_PREFIX}active:{cid}"


# --------------------------------------------------------------------------- #
# locking / parallelism
# --------------------------------------------------------------------------- #
async def _acquire(cid: str) -> bool:
    """Reserve the conversation lock *and* a global parallel slot."""

    redis = redis_client.get_redis()
    got = await cast(Awaitable[bool | None], redis.set(_active_key(cid), "1", nx=True))
    if not got:
        return False  # conversation already busy
    limit = get_settings().conversation_max_parallel
    count = int(await cast(Awaitable[int], redis.incr(_ACTIVE_COUNT)))
    if limit > 0 and count > limit:
        # No global slot: roll back both.
        await cast(Awaitable[int], redis.decr(_ACTIVE_COUNT))
        await cast(Awaitable[int], redis.delete(_active_key(cid)))
        return False
    return True


async def _release(cid: str) -> None:
    redis = redis_client.get_redis()
    existed = int(await cast(Awaitable[int], redis.delete(_active_key(cid))))
    if existed:
        value = int(await cast(Awaitable[int], redis.decr(_ACTIVE_COUNT)))
        if value < 0:
            await cast(Awaitable[bool], redis.set(_ACTIVE_COUNT, 0))


async def _pending_len(cid: str) -> int:
    redis = redis_client.get_redis()
    return int(await cast(Awaitable[int], redis.llen(_pending_key(cid))))


async def is_active(cid: str) -> bool:
    redis = redis_client.get_redis()
    return bool(await cast(Awaitable[int], redis.exists(_active_key(cid))))


# --------------------------------------------------------------------------- #
# core operations
# --------------------------------------------------------------------------- #
async def _try_pop_for_dispatch(cid: str) -> dict[str, Any] | None:
    """If a slot is free and work is pending, claim the conversation and pop one."""

    if await _pending_len(cid) == 0:
        return None
    if not await _acquire(cid):
        return None
    redis = redis_client.get_redis()
    front = await cast(Awaitable[str | None], redis.lpop(_pending_key(cid)))
    if front is None:  # raced empty
        await _release(cid)
        return None
    return json.loads(front)


async def enqueue(
    cid: str, content: str, *, role: str = "user", merge: bool = True
) -> dict[str, Any]:
    """Add a message; dispatch immediately if the conversation is idle.

    Returns ``{"status": "dispatched"|"queued", ...}``. On *dispatched* the
    conversation is now active and ``message`` is the turn to run; the caller
    must call :func:`complete` when the turn finishes.
    """

    redis = redis_client.get_redis()
    message = {"id": new_uuid(), "role": role, "content": content, "ts": time.time()}

    # Merge with the tail pending message when both are user turns.
    if merge and role == "user":
        tail = await cast(Awaitable[str | None], redis.lindex(_pending_key(cid), -1))
        if tail:
            prev = json.loads(tail)
            if prev.get("role") == "user":
                await cast(Awaitable[str | None], redis.rpop(_pending_key(cid)))
                message["content"] = f"{prev['content']}\n\n{content}"
                message["merged_count"] = int(prev.get("merged_count", 1)) + 1

    await cast(Awaitable[int], redis.rpush(_pending_key(cid), json.dumps(message)))

    dispatched = await _try_pop_for_dispatch(cid)
    if dispatched is not None:
        return {
            "status": "dispatched",
            "conversation_id": cid,
            "message": dispatched,
            "pending": await _pending_len(cid),
        }
    return {
        "status": "queued",
        "conversation_id": cid,
        "position": await _pending_len(cid),
        "pending": await _pending_len(cid),
    }


async def complete(cid: str) -> dict[str, Any] | None:
    """Finish the active turn and dispatch the next pending message, if any."""

    await _release(cid)
    return await _try_pop_for_dispatch(cid)


async def dispatch_next(cid: str) -> dict[str, Any] | None:
    """Try to start the next pending message (e.g. after a slot frees up)."""

    return await _try_pop_for_dispatch(cid)


async def status(cid: str) -> dict[str, Any]:
    redis = redis_client.get_redis()
    raw = await cast(Awaitable[list[str]], redis.lrange(_pending_key(cid), 0, -1))
    items = [json.loads(x) for x in raw]
    return {
        "conversation_id": cid,
        "active": await is_active(cid),
        "pending": len(items),
        "items": items,
        "active_total": int(await cast(Awaitable[Any], redis.get(_ACTIVE_COUNT)) or 0),
    }


async def clear(cid: str) -> None:
    """Drop all pending messages and release the conversation (admin/reset)."""

    redis = redis_client.get_redis()
    await cast(Awaitable[int], redis.delete(_pending_key(cid)))
    await _release(cid)
