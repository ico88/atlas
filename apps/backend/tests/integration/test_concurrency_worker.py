"""Concurrency-limit enforcement in the worker (spec §7)."""

from __future__ import annotations

import asyncio

import pytest
from app.core.config import get_settings
from app.models.task import TaskStatus
from app.schemas.task import TaskCreate
from app.services import queue, task_service
from app.worker import worker


@pytest.mark.asyncio
async def test_global_limit_defers_second_task(session, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "max_concurrent_global", 1)
    monkeypatch.setattr(settings, "worker_dummy_duration", 0.1)

    a = await task_service.create_task(session, TaskCreate(title="a"))
    b = await task_service.create_task(session, TaskCreate(title="b"))

    # Run both concurrently: only one slot is available, so the other defers.
    await asyncio.gather(worker.process_task(a.id), worker.process_task(b.id))

    await session.refresh(a)
    await session.refresh(b)
    statuses = {a.status, b.status}
    assert TaskStatus.COMPLETED.value in statuses
    # Exactly one completed; the other was requeued (still QUEUED) onto the
    # delayed queue.
    assert sorted(statuses) == sorted(
        {TaskStatus.COMPLETED.value, TaskStatus.QUEUED.value}
    )
    assert await queue.delayed_depth() == 1
