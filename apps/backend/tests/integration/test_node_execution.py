"""Integration tests for capability-based scheduling + remote execution (M4)."""

from __future__ import annotations

import pytest
from app.services import queue

BUILD_NODE = {
    "node_id": "builder-1",
    "capabilities": {"build": True, "test": True},
}


async def _register(client, node):
    return (await client.post("/api/v1/nodes/register", json=node)).json()


@pytest.mark.asyncio
async def test_capability_task_not_enqueued_locally(client):
    resp = await client.post(
        "/api/v1/tasks", json={"title": "build it", "required_capability": "build"}
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "QUEUED"
    assert resp.json()["required_capability"] == "build"
    # It must NOT go on the local worker queue — it waits for a node.
    assert await queue.queue_depth() == 0


@pytest.mark.asyncio
async def test_node_claims_executes_and_reports(client):
    await _register(client, BUILD_NODE)
    task = (
        await client.post(
            "/api/v1/tasks", json={"title": "compile", "required_capability": "build"}
        )
    ).json()

    claim = await client.post("/api/v1/nodes/builder-1/claim-task")
    assert claim.status_code == 200
    claimed = claim.json()
    assert claimed is not None
    assert claimed["id"] == task["id"]
    assert claimed["status"] == "RUNNING"
    assert claimed["assigned_node_id"]

    result = await client.post(
        f"/api/v1/tasks/{task['id']}/result",
        json={"status": "completed", "result": {"executed_by": "builder-1"}},
    )
    assert result.status_code == 200
    assert result.json()["status"] == "COMPLETED"
    assert result.json()["result"]["executed_by"] == "builder-1"


@pytest.mark.asyncio
async def test_node_without_capability_claims_nothing(client):
    await _register(client, {"node_id": "doc-1", "capabilities": {"document-processing": True}})
    await client.post("/api/v1/tasks", json={"title": "compile", "required_capability": "build"})

    claim = await client.post("/api/v1/nodes/doc-1/claim-task")
    assert claim.status_code == 200
    assert claim.json() is None  # no matching capability


@pytest.mark.asyncio
async def test_claim_is_exclusive(client):
    await _register(client, BUILD_NODE)
    await _register(client, {"node_id": "builder-2", "capabilities": {"build": True}})
    await client.post("/api/v1/tasks", json={"title": "only-one", "required_capability": "build"})

    first = (await client.post("/api/v1/nodes/builder-1/claim-task")).json()
    second = (await client.post("/api/v1/nodes/builder-2/claim-task")).json()
    assert first is not None
    assert second is None  # already claimed by builder-1


@pytest.mark.asyncio
async def test_remote_failure_retries_then_fails(client):
    await _register(client, BUILD_NODE)
    task = (
        await client.post(
            "/api/v1/tasks",
            json={"title": "flaky", "required_capability": "build", "max_retries": 1},
        )
    ).json()

    # First claim + failure -> requeued for retry.
    await client.post("/api/v1/nodes/builder-1/claim-task")
    r1 = await client.post(
        f"/api/v1/tasks/{task['id']}/result", json={"status": "failed", "error": "boom"}
    )
    assert r1.json()["status"] == "QUEUED"
    assert r1.json()["retries"] == 1

    # Second claim + failure -> exhausted -> FAILED.
    await client.post("/api/v1/nodes/builder-1/claim-task")
    r2 = await client.post(
        f"/api/v1/tasks/{task['id']}/result", json={"status": "failed", "error": "boom again"}
    )
    assert r2.json()["status"] == "FAILED"


@pytest.mark.asyncio
async def test_result_requires_running_task(client):
    task = (
        await client.post(
            "/api/v1/tasks", json={"title": "x", "required_capability": "build"}
        )
    ).json()
    # Not claimed yet (still QUEUED) -> reporting a result is a conflict.
    resp = await client.post(
        f"/api/v1/tasks/{task['id']}/result", json={"status": "completed"}
    )
    assert resp.status_code == 409
