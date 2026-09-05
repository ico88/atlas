"""Concurrency reservation & preemption for deployments (multi-runtime Fase 4).

Before a request runs on a deployment it **reserves a slot**; the slot is released
when the request finishes. A deployment never runs more than its ``max_concurrency``
at once — this is the safe, stateful guard that keeps two big models from thrashing
the same GPU. State is a per-deployment counter in Redis (shared across instances).

Full preemption of an in-flight generation is out of scope (it needs the runtime to
honour a cancel); what is provided here is the **decision** (`should_preempt`) plus
the bookkeeping, so a caller that can cancel a low-priority background turn is able
to free a slot for an urgent one. The decision is pure and unit-tested.
"""

from __future__ import annotations

import logging

from app import redis_client

logger = logging.getLogger(__name__)

_SLOT_KEY = "atlas:res:dep:"  # active-request counter per deployment id


def can_admit(active: int, max_concurrency: int) -> bool:
    """Pure: whether one more request fits under the deployment's limit."""

    if max_concurrency <= 0:
        return True  # 0 => unlimited
    return active < max_concurrency


def should_preempt(incoming_priority: int, lowest_active_priority: int | None) -> bool:
    """Pure: whether an incoming request outranks the lowest active one enough to
    justify preempting it. ``None`` (nothing running) never preempts."""

    if lowest_active_priority is None:
        return False
    return incoming_priority > lowest_active_priority


async def active(deployment_id: str) -> int:
    raw = await redis_client.get_redis().get(_SLOT_KEY + deployment_id)
    try:
        return int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        return 0


async def acquire(deployment_id: str, *, max_concurrency: int) -> bool:
    """Try to reserve a slot. Returns False (and reserves nothing) when full."""

    r = redis_client.get_redis()
    current = await active(deployment_id)
    if not can_admit(current, max_concurrency):
        return False
    await r.incr(_SLOT_KEY + deployment_id)
    return True


async def release(deployment_id: str) -> None:
    r = redis_client.get_redis()
    # Never let the counter go negative (a double release, a lost acquire).
    current = await active(deployment_id)
    if current <= 0:
        await r.delete(_SLOT_KEY + deployment_id)
        return
    await r.decr(_SLOT_KEY + deployment_id)


class Reservation:
    """Async context manager: reserve on enter, release on exit. ``ok`` says
    whether a slot was actually secured (False => at capacity, caller should
    route elsewhere)."""

    def __init__(self, deployment_id: str, *, max_concurrency: int) -> None:
        self._id = deployment_id
        self._max = max_concurrency
        self.ok = False

    async def __aenter__(self) -> Reservation:
        self.ok = await acquire(self._id, max_concurrency=self._max)
        return self

    async def __aexit__(self, *exc) -> None:
        if self.ok:
            await release(self._id)
