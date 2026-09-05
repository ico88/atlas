"""Fault-injection, failover & recovery suite (ROADMAP PR 26 — Quality).

Where the per-service tests prove each primitive in isolation, this suite injects
realistic *failures* and asserts the system recovers by itself, end to end:

- a local worker crashes mid-task    -> the scheduler reclaims and re-enqueues it;
- a dead owner's late writes are fenced out (no corruption after reclaim);
- repeated crashes exhaust retries    -> the task FAILS instead of looping forever;
- a remote node dies                  -> its task returns to the claim pool;
- the backend dies mid-chat           -> orphaned "pending" replies are recovered;
- the HA leader dies                  -> a standby takes over within the lease TTL.

All hermetic: file-backed SQLite + fake Redis, no external services, no sleeps.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from app.models.base import utcnow
from app.models.conversation import ChatMode, Conversation, Message, MessageRole
from app.models.task import TaskStatus
from app.schemas.task import TaskCreate
from app.services import chat_service, leadership_service, scheduler_service, task_service


async def _running(session, **over):
    """A RUNNING task holding a fresh 60s lease (a worker actively on it)."""
    data = {"title": "t", "type": "dummy", "max_retries": 2}
    data.update(over)
    task = await task_service.create_task(session, TaskCreate(**data))
    await task_service.mark_running(session, task)
    token = await scheduler_service.acquire_lease(session, task, ttl=60)
    return task, token


async def _crash(session, task):
    """Inject a worker/node crash: the lease is no longer renewed and expires."""
    task.lease_expires_at = utcnow() - timedelta(seconds=1)
    await session.commit()
    await session.refresh(task)


# --------------------------------------------------------------------------- #
# Worker crash -> reclaim + fencing
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_local_worker_crash_is_reclaimed_and_fenced(session):
    task, dead_token = await _running(session)
    await _crash(session, task)

    reclaimed = await scheduler_service.reclaim_expired(session)

    assert [t.id for t in reclaimed] == [task.id]
    await session.refresh(task)
    assert task.status == TaskStatus.RETRYING.value  # back in the local queue
    assert task.retries == 1
    assert task.lease_token != dead_token  # token rotated -> old owner fenced out
    assert task.lease_expires_at is None

    # The crashed owner "comes back from the dead" and tries to finish: its stale
    # token must be rejected so it cannot clobber the reclaimed task's state.
    assert await scheduler_service.renew_lease(session, task, dead_token) is False
    assert await scheduler_service.save_checkpoint(session, task, dead_token, {"x": 1}) is False
    await session.refresh(task)
    assert task.checkpoint in (None, {})  # untouched by the fenced write


@pytest.mark.asyncio
async def test_repeated_crashes_exhaust_retries_no_infinite_loop(session):
    task, _ = await _running(session, max_retries=1)

    await _crash(session, task)
    assert await scheduler_service.reclaim_expired(session)  # attempt 1 -> RETRYING
    await session.refresh(task)
    assert task.retries == 1

    # It is picked up again and crashes again: retries are now exhausted.
    await task_service.mark_running(session, task)
    await scheduler_service.acquire_lease(session, task, ttl=60)
    await _crash(session, task)
    reclaimed = await scheduler_service.reclaim_expired(session)

    assert reclaimed == []  # a FAILED task is not re-enqueued
    await session.refresh(task)
    assert task.status == TaskStatus.FAILED.value
    assert task.error and "lease expired" in task.error


@pytest.mark.asyncio
async def test_remote_node_crash_returns_task_to_claim_pool(session):
    # A task with a required capability runs on a remote node.
    task, _ = await _running(session, required_capability="build")
    task.assigned_node_id = "node-a"
    await session.commit()
    await _crash(session, task)

    reclaimed = await scheduler_service.reclaim_expired(session)

    assert reclaimed == []  # remote tasks are re-claimed by nodes, not locally run
    await session.refresh(task)
    assert task.status == TaskStatus.QUEUED.value
    assert task.assigned_node_id is None  # detached from the dead node


@pytest.mark.asyncio
async def test_healthy_lease_is_not_reclaimed(session):
    task, token = await _running(session)  # lease still valid
    assert await scheduler_service.reclaim_expired(session) == []
    await session.refresh(task)
    assert task.status == TaskStatus.RUNNING.value
    assert task.lease_token == token


# --------------------------------------------------------------------------- #
# Backend crash mid-chat -> pending reply recovery
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_crashed_chat_reply_is_recovered_on_startup(session):
    convo = Conversation(title="c", mode=ChatMode.AUTO.value)
    session.add(convo)
    await session.flush()
    orphan = Message(
        conversation_id=convo.id,
        role=MessageRole.ASSISTANT.value,
        content="partial answer so f",  # streamed before the crash
        status="pending",
    )
    done = Message(
        conversation_id=convo.id,
        role=MessageRole.ASSISTANT.value,
        content="finished",
        status="complete",
    )
    session.add_all([orphan, done])
    await session.commit()

    recovered = await chat_service.recover_pending_replies()

    assert recovered == 1
    await session.refresh(orphan)
    await session.refresh(done)
    assert orphan.status == "error"  # no longer stuck "working" forever
    assert orphan.content == "partial answer so f"  # partial text preserved
    assert done.status == "complete"  # a finished reply is untouched

    # Idempotent: a second startup finds nothing left to recover.
    assert await chat_service.recover_pending_replies() == 0


# --------------------------------------------------------------------------- #
# HA leader crash -> automatic failover
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_ha_leader_crash_fails_over_to_standby(monkeypatch, fake_redis):
    settings = leadership_service.get_settings()
    monkeypatch.setattr(settings, "ha_enabled", True, raising=False)

    monkeypatch.setattr(leadership_service, "instance_id", lambda: "A")
    assert await leadership_service.try_acquire_leadership(ttl=30) is True
    assert await leadership_service.is_leader() is True

    # B is a standby: while A holds the lease, B cannot become leader.
    monkeypatch.setattr(leadership_service, "instance_id", lambda: "B")
    assert await leadership_service.try_acquire_leadership(ttl=30) is False
    assert await leadership_service.is_leader() is False

    # Inject A's crash: its lease expires (here, is dropped) and B takes over —
    # automatic failover with no human action.
    await fake_redis.delete("atlas:ha:leader")
    assert await leadership_service.try_acquire_leadership(ttl=30) is True
    assert await leadership_service.current_leader() == "B"
    assert await leadership_service.is_leader() is True

    # The recovered A is now the standby and must not seize leadership back.
    monkeypatch.setattr(leadership_service, "instance_id", lambda: "A")
    assert await leadership_service.try_acquire_leadership(ttl=30) is False
    assert await leadership_service.is_leader() is False
