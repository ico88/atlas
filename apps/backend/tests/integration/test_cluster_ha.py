"""Control-plane HA: leader election + cluster status (ROADMAP PR 9)."""

from __future__ import annotations

import pytest
from app.services import leadership_service


@pytest.mark.asyncio
async def test_single_node_is_always_leader(client):
    # HA disabled (default): this instance is the leader, cluster endpoint works.
    body = (await client.get("/api/v1/cluster")).json()
    assert body["ha_enabled"] is False
    assert body["is_leader"] is True
    assert any(m["self"] for m in body["members"])


@pytest.mark.asyncio
async def test_lease_is_exclusive_and_failover(monkeypatch):
    from app.core import config

    # Force two distinct instance ids sharing one (fake) Redis, HA on.
    real = config.get_settings()

    class _S:
        ha_enabled = True
        ha_lease_ttl = 30

        def __getattr__(self, k):
            return getattr(real, k)

    monkeypatch.setattr(leadership_service, "get_settings", lambda: _S())

    # Instance A grabs the lease; B cannot while A holds it.
    monkeypatch.setattr(leadership_service, "instance_id", lambda: "A")
    assert await leadership_service.try_acquire_leadership(30) is True
    monkeypatch.setattr(leadership_service, "instance_id", lambda: "B")
    assert await leadership_service.try_acquire_leadership(30) is False
    assert await leadership_service.is_leader() is False
    monkeypatch.setattr(leadership_service, "instance_id", lambda: "A")
    assert await leadership_service.is_leader() is True

    # Simulate A dying: drop the lease, then B can take over (failover).
    from app import redis_client

    await redis_client.get_redis().delete("atlas:ha:leader")
    monkeypatch.setattr(leadership_service, "instance_id", lambda: "B")
    assert await leadership_service.try_acquire_leadership(30) is True
    assert await leadership_service.is_leader() is True


@pytest.mark.asyncio
async def test_members_registry_lists_instances(monkeypatch):
    monkeypatch.setattr(leadership_service, "instance_id", lambda: "node-a")
    await leadership_service.register_instance(30)
    monkeypatch.setattr(leadership_service, "instance_id", lambda: "node-b")
    await leadership_service.register_instance(30)
    members = {m["id"] for m in await leadership_service.list_members()}
    assert {"node-a", "node-b"} <= members
