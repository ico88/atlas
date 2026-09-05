"""Integration tests for fleet compliance & remediation (PR 24 / PR 25)."""

from __future__ import annotations

import pytest
from app.models.base import utcnow
from app.models.node import Node


async def _node(session, ref, *, version="1.0.0", online=True, cap="build"):
    session.add(
        Node(
            node_id=ref,
            label=ref,
            version=version,
            status="online" if online else "offline",
            last_heartbeat=utcnow() if online else None,
            capabilities={cap: True},
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_desired_state_and_compliance_report(client, session):
    await _node(session, "n1", version="1.0.0")
    await _node(session, "n2", version="0.9.0")  # drift

    await client.put(
        "/api/v1/fleet/desired",
        json={"target_version": "1.0.0", "required_capabilities": ["build"], "min_online": 1},
    )
    report = (await client.get("/api/v1/fleet/compliance")).json()
    assert report["summary"]["total"] == 2
    assert report["summary"]["compliant"] == 1
    drifted = next(n for n in report["nodes"] if n["node_ref"] == "n2")
    assert drifted["compliant"] is False
    assert drifted["recommended_action"] == "remediate"


@pytest.mark.asyncio
async def test_auto_remediate_sets_desired_version(client, session):
    await _node(session, "n1", version="0.9.0")
    await client.put("/api/v1/fleet/desired", json={"target_version": "1.2.0"})

    after = (await client.post("/api/v1/fleet/auto-remediate")).json()
    assert after["summary"]["total"] == 1
    # An audit event was recorded and the node was told to move to 1.2.0.
    events = (await client.get("/api/v1/fleet/remediation-events")).json()
    assert any(e["action"] == "remediate" and e["automatic"] for e in events)
    node = next(n for n in (await client.get("/api/v1/nodes")).json()["items"]
                if n["node_id"] == "n1")
    assert node.get("desired_version") == "1.2.0"


@pytest.mark.asyncio
async def test_quarantine_excludes_from_scheduling_then_reinstate(client, session):
    from app.models.task import Task, TaskStatus
    from app.services import node_service

    await _node(session, "n1", cap="build")
    session.add(Task(title="t", type="dummy", status=TaskStatus.QUEUED.value,
                     required_capability="build"))
    await session.commit()

    # Quarantine -> the node cannot claim the matching task.
    q = await client.post(
        "/api/v1/fleet/remediate", json={"node_ref": "n1", "action": "quarantine"}
    )
    assert q.status_code == 200
    node = await node_service.get_node_by_ref(session, "n1")
    session.expunge_all()
    node = await node_service.get_node_by_ref(session, "n1")
    assert await node_service.claim_task(session, node) is None

    # Reinstate -> it can claim again.
    await client.post("/api/v1/fleet/remediate", json={"node_ref": "n1", "action": "reinstate"})
    session.expunge_all()
    node = await node_service.get_node_by_ref(session, "n1")
    claimed = await node_service.claim_task(session, node)
    assert claimed is not None
