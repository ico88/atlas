"""Integration tests for the ALMA orchestrator (M5)."""

from __future__ import annotations

import time

import pytest
from app.models.task import TaskStatus
from app.schemas.task import TaskCreate
from app.services import queue, task_service
from app.worker import worker


async def _drain(max_steps: int = 80) -> None:
    for _ in range(max_steps):
        await queue.promote_due(now=time.time() + 3600)
        if await queue.queue_depth() == 0:
            break
        task_id = await queue.dequeue(timeout=1)
        if task_id is None:
            break
        await worker.process_task(task_id)


@pytest.mark.asyncio
async def test_alma_default_plan_completes_and_aggregates(session):
    alma = await task_service.create_task(
        session, TaskCreate(title="Build feature X", type="alma")
    )
    await queue.enqueue(alma.id)
    await _drain()

    await session.refresh(alma)
    assert alma.status == TaskStatus.COMPLETED.value
    assert alma.result is not None
    assert alma.result["subtask_count"] == 3
    assert alma.result["completed"] == 3

    subtasks = await task_service.list_subtasks(session, alma.id)
    assert len(subtasks) == 3
    assert all(s.status == TaskStatus.COMPLETED.value for s in subtasks)
    # Correlation id propagates from ALMA to every subtask (§12).
    assert all(s.correlation_id == alma.correlation_id for s in subtasks)


@pytest.mark.asyncio
async def test_alma_explicit_dag_with_parallel_steps(session):
    plan = {
        "plan": [
            {"key": "a", "title": "A"},
            {"key": "b", "title": "B"},
            {"key": "c", "title": "C", "depends_on": ["a", "b"]},
        ]
    }
    alma = await task_service.create_task(
        session, TaskCreate(title="fan-in", type="alma", payload=plan)
    )
    await queue.enqueue(alma.id)
    await _drain()

    await session.refresh(alma)
    assert alma.status == TaskStatus.COMPLETED.value

    subs = {s.title: s for s in await task_service.list_subtasks(session, alma.id)}
    assert set(subs) == {"A", "B", "C"}
    # C (fan-in) must start only after A and B both finished.
    assert subs["C"].started_at >= subs["A"].completed_at
    assert subs["C"].started_at >= subs["B"].completed_at


@pytest.mark.asyncio
async def test_alma_fails_when_subtask_fails(session):
    plan = {"plan": [{"key": "x", "title": "X", "payload": {"fail": True}}]}
    alma = await task_service.create_task(
        session, TaskCreate(title="doomed", type="alma", payload=plan)
    )
    await queue.enqueue(alma.id)
    await _drain()

    await session.refresh(alma)
    assert alma.status == TaskStatus.FAILED.value
    assert "subtask" in (alma.error or "")


@pytest.mark.asyncio
async def test_alma_subtasks_endpoint(client):
    created = await client.post(
        "/api/v1/tasks", json={"title": "plan it", "type": "alma"}
    )
    alma_id = created.json()["id"]
    # Process so decomposition happens.
    await _drain()

    resp = await client.get(f"/api/v1/tasks/{alma_id}/subtasks")
    assert resp.status_code == 200
    assert len(resp.json()) == 3
