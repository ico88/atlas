"""Integration tests for the local worker lifecycle."""

from __future__ import annotations

import pytest
from app.db import get_sessionmaker
from app.models.task import TaskStatus
from app.schemas.task import TaskCreate
from app.services import queue, task_service
from app.worker import worker


@pytest.mark.asyncio
async def test_worker_drives_task_to_completed(session):
    task = await task_service.create_task(session, TaskCreate(title="dummy", payload={"a": 1}))
    await queue.enqueue(task.id)

    # Worker pops from the queue and processes the task.
    popped = await queue.dequeue(timeout=1)
    assert popped == task.id
    await worker.process_task(task.id)

    # Re-open a fresh session (simulating a separate process / restart) and
    # verify the persisted final state and full event trail.
    async with get_sessionmaker()() as fresh:
        reloaded = await task_service.get_task(fresh, task.id)
        assert reloaded is not None
        assert reloaded.status == TaskStatus.COMPLETED.value
        assert reloaded.result is not None
        assert reloaded.started_at is not None
        assert reloaded.completed_at is not None

        events = await task_service.list_events(fresh, task.id)
        statuses = [e.status for e in events]
        assert statuses == ["QUEUED", "RUNNING", "COMPLETED"]


@pytest.mark.asyncio
async def test_worker_skips_cancelled_task(session):
    task = await task_service.create_task(session, TaskCreate(title="cancel"))
    await task_service.cancel_task(session, task)

    await worker.process_task(task.id)

    async with get_sessionmaker()() as fresh:
        reloaded = await task_service.get_task(fresh, task.id)
        assert reloaded is not None
        assert reloaded.status == TaskStatus.CANCELLED.value
