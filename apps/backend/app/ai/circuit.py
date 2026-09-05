"""Per-runtime circuit breaker (multi-runtime Fase 2).

A runtime that keeps failing is taken out of rotation instead of being retried on
every request. State lives in Redis (shared across control-plane instances):

    CLOSED  — healthy, requests flow.
    OPEN    — too many consecutive failures; skipped until the cooldown elapses.
    (probe) — after the cooldown the next request is allowed through; success
              closes the circuit, failure re-opens it.

The decision itself is a pure function so it is unit-tested without Redis.
"""

from __future__ import annotations

import logging
import time

from app import redis_client
from app.core.config import get_settings

logger = logging.getLogger(__name__)

_FAIL_KEY = "atlas:cb:fail:"  # consecutive failure count
_OPEN_KEY = "atlas:cb:open:"  # unix ts until which the circuit stays open


def should_open(failures: int, threshold: int) -> bool:
    """Pure: whether this many consecutive failures trips the breaker."""

    return threshold > 0 and failures >= threshold


async def record_failure(runtime_key: str) -> int:
    """Count a failure; open the circuit when the threshold is reached."""

    settings = get_settings()
    r = redis_client.get_redis()
    failures = int(await r.incr(_FAIL_KEY + runtime_key))
    if should_open(failures, settings.runtime_circuit_threshold):
        await r.set(
            _OPEN_KEY + runtime_key,
            str(time.time() + settings.runtime_circuit_cooldown),
            ex=int(settings.runtime_circuit_cooldown) + 1,
        )
        logger.warning(
            "circuit opened for runtime",
            extra={
                "event": "circuit_open",
                "context": {"runtime": runtime_key, "failures": failures},
            },
        )
    return failures


async def record_success(runtime_key: str) -> None:
    """Clear failures and close the circuit."""

    r = redis_client.get_redis()
    await r.delete(_FAIL_KEY + runtime_key, _OPEN_KEY + runtime_key)


async def is_open(runtime_key: str, *, now: float | None = None) -> bool:
    """Whether the circuit is currently open (cooldown not yet elapsed)."""

    raw = await redis_client.get_redis().get(_OPEN_KEY + runtime_key)
    if raw is None:
        return False
    try:
        open_until = float(raw)
    except (TypeError, ValueError):
        return False
    return (now or time.time()) < open_until


async def state(runtime_key: str) -> str:
    return "OPEN" if await is_open(runtime_key) else "CLOSED"
