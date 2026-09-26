"""Control-plane leader election & cluster registry (ROADMAP PR 9).

Multiple control-plane instances coordinate through a short-lived Redis **lease**:
whoever holds ``atlas:ha:leader`` is the leader and is the only instance that runs
singleton background work (the autonomous proposer, etc.). The lease has a TTL, so
if the leader dies another instance takes over within ``ha_lease_ttl`` seconds —
automatic failover with no human action.

Each instance also registers a heartbeat key so the cluster's members are visible.
When HA is disabled (single-node), this instance is always the leader and nothing
changes.

Honest scope: this is single-Redis coordination. For true HA the Redis/DB layer
must itself be highly available (documented in HA.md); the election logic here is
the coordination primitive.
"""

from __future__ import annotations

import logging
import os
import socket

from app import redis_client
from app.core.config import get_settings
from app.models.base import utcnow

logger = logging.getLogger(__name__)

_LEADER_KEY = "atlas:ha:leader"
_MEMBER_PREFIX = "atlas:ha:member:"


def instance_id() -> str:
    return get_settings().instance_id or f"{socket.gethostname()}-{os.getpid()}"


def _s(value: object) -> str | None:
    if value is None:
        return None
    return value.decode() if isinstance(value, bytes) else str(value)


async def try_acquire_leadership(ttl: int | None = None) -> bool:
    """Acquire or renew the leader lease. Returns whether we hold it now."""

    ttl = ttl or get_settings().ha_lease_ttl
    r = redis_client.get_redis()
    me = instance_id()
    # Grab it if free.
    if await r.set(_LEADER_KEY, me, nx=True, ex=ttl):
        return True
    # Otherwise renew only if we already hold it.
    if _s(await r.get(_LEADER_KEY)) == me:
        await r.set(_LEADER_KEY, me, ex=ttl)
        return True
    return False


async def current_leader() -> str | None:
    return _s(await redis_client.get_redis().get(_LEADER_KEY))


async def is_leader() -> bool:
    """True in single-node mode; in HA mode, only when we hold the lease."""

    if not get_settings().ha_enabled:
        return True
    return await current_leader() == instance_id()


async def register_instance(ttl: int | None = None) -> None:
    ttl = (ttl or get_settings().ha_lease_ttl) * 3
    await redis_client.get_redis().set(
        _MEMBER_PREFIX + instance_id(), utcnow().isoformat(), ex=ttl
    )


async def list_members() -> list[dict]:
    r = redis_client.get_redis()
    leader = await current_leader()
    me = instance_id()
    members: dict[str, str | None] = {}
    async for key in r.scan_iter(match=_MEMBER_PREFIX + "*"):
        k = _s(key) or ""
        mid = k[len(_MEMBER_PREFIX):]
        if mid:
            members[mid] = _s(await r.get(k))
    members.setdefault(me, utcnow().isoformat())  # always include self
    return [
        {"id": mid, "last_seen": seen, "leader": mid == leader, "self": mid == me}
        for mid, seen in sorted(members.items())
    ]


async def cluster_status() -> dict:
    leader = await current_leader()
    me = instance_id()
    return {
        "instance_id": me,
        "leader": leader,
        "is_leader": (leader == me) if get_settings().ha_enabled else True,
        "ha_enabled": get_settings().ha_enabled,
        "lease_ttl": get_settings().ha_lease_ttl,
        "members": await list_members(),
    }
