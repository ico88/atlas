"""Integration tests for fleet deployments (ROADMAP PR 21 / PR 22)."""

from __future__ import annotations

import pytest
from app.models.base import utcnow
from app.models.node import Node


async def _seed_nodes(session, n: int, *, version="1.0.0", online=True) -> list[str]:
    refs = []
    for i in range(n):
        ref = f"node-{i}"
        session.add(
            Node(
                node_id=ref,
                label=ref,
                version=version,
                status="online" if online else "offline",
                last_heartbeat=utcnow() if online else None,
            )
        )
        refs.append(ref)
    await session.commit()
    return refs


@pytest.mark.asyncio
async def test_canary_gate_then_rolling_complete(client, session):
    await _seed_nodes(session, 3)

    dep = (
        await client.post(
            "/api/v1/deployments",
            json={"target_version": "2.0.0", "canary_count": 1},
        )
    ).json()
    assert dep["status"] == "CANARY"
    canary = [t for t in dep["targets"] if t["wave"] == "canary"]
    rollout = [t for t in dep["targets"] if t["wave"] == "rollout"]
    assert len(canary) == 1 and len(rollout) == 2
    assert canary[0]["status"] == "UPDATING"
    assert all(t["status"] == "PENDING" for t in rollout)

    dep_id = dep["id"]
    # Canary reports healthy on the target -> gate passes -> ROLLING.
    await client.post(
        f"/api/v1/deployments/{dep_id}/report",
        json={"node_ref": canary[0]["node_ref"], "version": "2.0.0", "healthy": True},
    )
    advanced = (await client.post(f"/api/v1/deployments/{dep_id}/advance")).json()
    assert advanced["status"] == "ROLLING"
    assert all(t["status"] == "UPDATING" for t in advanced["targets"] if t["wave"] == "rollout")

    # Rollout reports healthy -> COMPLETED.
    for t in advanced["targets"]:
        if t["wave"] == "rollout":
            await client.post(
                f"/api/v1/deployments/{dep_id}/report",
                json={"node_ref": t["node_ref"], "version": "2.0.0", "healthy": True},
            )
    done = (await client.post(f"/api/v1/deployments/{dep_id}/advance")).json()
    assert done["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_canary_failure_rolls_back(client, session):
    await _seed_nodes(session, 3)
    dep = (
        await client.post(
            "/api/v1/deployments", json={"target_version": "2.0.0", "canary_count": 1}
        )
    ).json()
    dep_id = dep["id"]
    canary = next(t for t in dep["targets"] if t["wave"] == "canary")

    # Canary comes back unhealthy -> the gate rolls the whole thing back.
    await client.post(
        f"/api/v1/deployments/{dep_id}/report",
        json={"node_ref": canary["node_ref"], "version": "2.0.0", "healthy": False},
    )
    out = (await client.post(f"/api/v1/deployments/{dep_id}/advance")).json()
    assert out["status"] == "ROLLED_BACK"

    # The node's desired version was reverted to its previous version.
    node = next(n for n in (await client.get("/api/v1/nodes")).json()["items"]
                if n["node_id"] == canary["node_ref"])
    assert node.get("desired_version") in (canary["from_version"], "1.0.0", None)


@pytest.mark.asyncio
async def test_offline_and_incompatible_are_skipped(client, session):
    await _seed_nodes(session, 1, version="1.0.0", online=True)
    await _seed_nodes_extra_offline(session)
    dep = (
        await client.post(
            "/api/v1/deployments",
            json={"target_version": "2.0.0", "canary_count": 1, "min_compatible": "1.0.0"},
        )
    ).json()
    statuses = {t["node_ref"]: t["status"] for t in dep["targets"]}
    assert statuses.get("offline-x") == "SKIPPED_OFFLINE"
    assert statuses.get("old-y") == "INCOMPATIBLE"


async def _seed_nodes_extra_offline(session):
    session.add(Node(node_id="offline-x", label="x", version="1.0.0", status="offline"))
    session.add(
        Node(
            node_id="old-y",
            label="y",
            version="0.5.0",
            status="online",
            last_heartbeat=utcnow(),
        )
    )
    await session.commit()
