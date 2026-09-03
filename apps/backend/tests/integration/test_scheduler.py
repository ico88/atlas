"""Resilient scheduler tests (ROADMAP PR 8): lease, fencing, reclaim, failover."""

from __future__ import annotations

from datetime import timedelta

import pytest
from app.models.base import utcnow
from app.models.task import TaskStatus
from app.schemas.task import TaskCreate
from app.services import scheduler_service, task_service


async def _running_task(session, **over):
    data = {"title": "t", "type": "dummy", "max_retries": 2}
    data.update(over)
    task = await task_service.create_task(session, TaskCreate(**data))
    await task_service.mark_running(session, task)
    token = await scheduler_service.acquire_lease(session, task, ttl=60)
    return task, token


async def _expire(session, task):
    task.lease_expires_at = utcnow() - timedelta(seconds=5)
    await session.commit()
    await session.refresh(task)


@pytest.mark.asyncio
async def test_acquire_lease_sets_token_and_expiry(session):
    task, token = await _running_task(session)
    assert token and task.lease_token == token
    assert task.lease_expires_at is not None
    assert task.heartbeat_at is not None
    assert not scheduler_service.is_lease_expired(task)


@pytest.mark.asyncio
async def test_renew_requires_current_token(session):
    task, token = await _running_task(session)
    assert await scheduler_service.renew_lease(session, task, token) is True
    # A stale/wrong token is fenced out.
    assert await scheduler_service.renew_lease(session, task, "wrong-token") is False


@pytest.mark.asyncio
async def test_checkpoint_persists_and_is_fenced(session):
    task, token = await _running_task(session)
    ok = await scheduler_service.save_checkpoint(session, task, token, {"step": 3})
    assert ok is True
    assert task.checkpoint == {"step": 3}
    assert await scheduler_service.save_checkpoint(session, task, "nope", {"step": 9}) is False
    assert task.checkpoint == {"step": 3}  # unchanged after a fenced write


@pytest.mark.asyncio
async def test_reclaim_local_task_requeues_and_bumps_retries(session):
    task, old_token = await _running_task(session)
    await _expire(session, task)

    reclaimed = await scheduler_service.reclaim_expired(session)
    assert [t.id for t in reclaimed] == [task.id]

    await session.refresh(task)
    assert task.status == TaskStatus.RETRYING.value
    assert task.retries == 1
    assert task.lease_token != old_token  # fenced
    assert task.lease_expires_at is None


@pytest.mark.asyncio
async def test_reclaim_remote_task_returns_to_pool(session):
    task, _ = await _running_task(session, required_capability="build")
    task.assigned_node_id = "node-x"
    await session.commit()
    await _expire(session, task)

    reclaimed = await scheduler_service.reclaim_expired(session)
    # Remote tasks go back to the QUEUED claim pool (not the local enqueue list).
    assert reclaimed == []
    await session.refresh(task)
    assert task.status == TaskStatus.QUEUED.value
    assert task.assigned_node_id is None
    assert task.retries == 1


@pytest.mark.asyncio
async def test_reclaim_fails_when_retries_exhausted(session):
    task, _ = await _running_task(session, max_retries=0)
    await _expire(session, task)

    reclaimed = await scheduler_service.reclaim_expired(session)
    assert reclaimed == []
    await session.refresh(task)
    assert task.status == TaskStatus.FAILED.value
    assert "lease expired" in (task.error or "")


@pytest.mark.asyncio
async def test_reclaim_leaves_fresh_leases_untouched(session):
    task, token = await _running_task(session)  # fresh 60s lease
    reclaimed = await scheduler_service.reclaim_expired(session)
    assert reclaimed == []
    await session.refresh(task)
    assert task.status == TaskStatus.RUNNING.value
    assert task.lease_token == token


@pytest.mark.asyncio
async def test_late_completion_after_reclaim_is_rejected(client, session):
    # A remote task reclaimed back to QUEUED must reject a late node result (409).
    task, _ = await _running_task(session, required_capability="build")
    await _expire(session, task)
    await scheduler_service.reclaim_expired(session)

    resp = await client.post(
        f"/api/v1/tasks/{task.id}/result",
        json={"status": "completed", "result": {"stale": True}},
    )
    assert resp.status_code == 409
