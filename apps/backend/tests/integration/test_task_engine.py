"""Integration tests for M3 task-engine features:
concurrency limits, retries with backoff, dependencies (DAG), idempotency.
"""

from __future__ import annotations

import time

import pytest
from app.models.task import TaskStatus
from app.schemas.task import TaskCreate
from app.services import concurrency, queue, task_service
from app.worker import worker


async def _drain(max_steps: int = 60) -> None:
    """Run the scheduler + worker until the queues are empty."""

    for _ in range(max_steps):
        await queue.promote_due(now=time.time() + 3600)  # force all delayed ready
        if await queue.queue_depth() == 0:
            break
        task_id = await queue.dequeue(timeout=1)
        if task_id is None:
            break
        await worker.process_task(task_id)


# --- concurrency limiter -----------------------------------------------------


@pytest.mark.asyncio
async def test_concurrency_limiter_acquire_release():
    scopes = {"atlas:concurrency:global": 1}
    first = await concurrency.acquire(scopes)
    assert first is not None
    # Limit reached -> second acquire fails and rolls back.
    assert await concurrency.acquire(scopes) is None
    await concurrency.release(first)
    assert await concurrency.acquire(scopes) is not None


def test_build_scopes_skips_unlimited():
    scopes = concurrency.build_scopes(
        owner_id="u1",
        task_type="dummy",
        limits={"global": 0, "per_user": 2, "per_type": 0},
    )
    assert scopes == {"atlas:concurrency:user:u1": 2}


# --- retries -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_task_retries_then_succeeds(session):
    task = await task_service.create_task(
        session, TaskCreate(title="flaky", payload={"succeed_after": 2}, max_retries=3)
    )
    await queue.enqueue(task.id)
    await _drain()

    reloaded = await task_service.get_task(session, task.id)
    await session.refresh(reloaded)
    assert reloaded.status == TaskStatus.COMPLETED.value
    assert reloaded.retries == 2


@pytest.mark.asyncio
async def test_task_retries_exhausted_then_failed(session):
    task = await task_service.create_task(
        session, TaskCreate(title="broken", payload={"fail": True}, max_retries=2)
    )
    await queue.enqueue(task.id)
    await _drain()

    reloaded = await task_service.get_task(session, task.id)
    await session.refresh(reloaded)
    assert reloaded.status == TaskStatus.FAILED.value
    assert reloaded.retries == 2


# --- dependencies (DAG) ------------------------------------------------------


@pytest.mark.asyncio
async def test_dependency_gates_until_parent_completes(session, client):
    parent = await task_service.create_task(session, TaskCreate(title="parent"))
    child = await task_service.create_task(
        session, TaskCreate(title="child", depends_on=[parent.id])
    )
    assert child.status == TaskStatus.WAITING_DEPENDENCY.value
    # Child must NOT be enqueued yet.
    assert await queue.queue_depth() == 0

    await queue.enqueue(parent.id)
    await _drain()

    await session.refresh(parent)
    await session.refresh(child)
    assert parent.status == TaskStatus.COMPLETED.value
    assert child.status == TaskStatus.COMPLETED.value


# --- idempotency -------------------------------------------------------------


@pytest.mark.asyncio
async def test_idempotent_create(session):
    first = await task_service.create_task(
        session, TaskCreate(title="once", idempotency_key="k-1")
    )
    second = await task_service.create_task(
        session, TaskCreate(title="again", idempotency_key="k-1")
    )
    assert first.id == second.id


@pytest.mark.asyncio
async def test_create_with_dependency_via_api_not_enqueued(client):
    parent = (await client.post("/api/v1/tasks", json={"title": "p"})).json()
    resp = await client.post(
        "/api/v1/tasks", json={"title": "c", "depends_on": [parent["id"]]}
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "WAITING_DEPENDENCY"
    # Only the parent is on the queue.
    assert await queue.queue_depth() == 1
