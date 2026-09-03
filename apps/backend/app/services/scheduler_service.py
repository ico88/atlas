"""Resilient scheduling primitives (ROADMAP PR 8).

Adds crash-tolerance to the task engine on top of the existing queue/retry logic:

- **lease** — a RUNNING task holds a time-boxed lease with a **fencing token**;
- **heartbeat / checkpoint** — the executor renews the lease and may persist a
  progress checkpoint so work can resume instead of restarting;
- **fencing** — renew/checkpoint require the current token, so a zombie worker
  whose lease was reclaimed cannot corrupt state;
- **failover** — ``reclaim_expired`` returns leases whose deadline passed to the
  queue (local) or the claim pool (remote), rotating the token so the dead
  owner's late writes are ignored; exhausted retries fail the task.

All timestamps tolerate naive datetimes from SQLite (the test DB).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.base import new_uuid, utcnow
from app.models.task import Task, TaskStatus
from app.services import task_service

logger = logging.getLogger(__name__)


def _aware(dt: datetime, ref: datetime) -> datetime:
    """Align tz-awareness of ``dt`` to ``ref`` for safe comparison."""

    if dt.tzinfo is None and ref.tzinfo is not None:
        return dt.replace(tzinfo=ref.tzinfo)
    if dt.tzinfo is not None and ref.tzinfo is None:
        return dt.replace(tzinfo=None)
    return dt


def lease_ttl() -> float:
    return get_settings().task_lease_seconds


async def acquire_lease(session: AsyncSession, task: Task, *, ttl: float | None = None) -> str:
    """Grant a fresh lease + fencing token to a task about to run. Commits."""

    ttl = ttl if ttl is not None else lease_ttl()
    token = new_uuid()
    now = utcnow()
    task.lease_token = token
    task.lease_expires_at = now + timedelta(seconds=ttl)
    task.heartbeat_at = now
    await session.commit()
    await session.refresh(task)
    return token


def is_current_token(task: Task, token: str | None) -> bool:
    return bool(task.lease_token) and task.lease_token == token


async def renew_lease(
    session: AsyncSession,
    task: Task,
    token: str,
    *,
    ttl: float | None = None,
    checkpoint: dict | None = None,
) -> bool:
    """Extend the lease and heartbeat (fencing-guarded). Returns False if fenced."""

    if not is_current_token(task, token):
        logger.warning(
            "rejected lease renew with stale token",
            extra={"event": "lease_fenced", "context": {"task_id": task.id}},
        )
        return False
    ttl = ttl if ttl is not None else lease_ttl()
    now = utcnow()
    task.lease_expires_at = now + timedelta(seconds=ttl)
    task.heartbeat_at = now
    if checkpoint is not None:
        task.checkpoint = checkpoint
    await session.commit()
    await session.refresh(task)
    return True


async def save_checkpoint(
    session: AsyncSession, task: Task, token: str, checkpoint: dict
) -> bool:
    """Persist a resume checkpoint (fencing-guarded)."""

    return await renew_lease(session, task, token, checkpoint=checkpoint)


def is_lease_expired(task: Task, *, now: datetime | None = None) -> bool:
    if task.status != TaskStatus.RUNNING.value or task.lease_expires_at is None:
        return False
    now = now or utcnow()
    return _aware(task.lease_expires_at, now) < now


async def reclaim_expired(session: AsyncSession, *, now: datetime | None = None) -> list[Task]:
    """Reclaim RUNNING tasks whose lease expired. Returns local tasks to re-enqueue.

    Local tasks with retries left return to RETRYING; remote tasks return to the
    QUEUED claim pool; exhausted tasks are FAILED. The fencing token is rotated so
    a late completion from the dead owner is ignored.
    """

    if not get_settings().scheduler_reclaim_enabled:
        return []
    now = now or utcnow()
    running = list(
        (
            await session.execute(
                select(Task).where(Task.status == TaskStatus.RUNNING.value)
            )
        )
        .scalars()
        .all()
    )
    to_enqueue: list[Task] = []
    for task in running:
        if not is_lease_expired(task, now=now):
            continue
        task.lease_token = new_uuid()  # fence out the old owner
        task.lease_expires_at = None
        error = "lease expired (worker/node unresponsive)"
        if task.retries < task.max_retries:
            task.retries += 1
            task.status = TaskStatus.QUEUED.value if not task_service.runs_locally(task) else (
                TaskStatus.RETRYING.value
            )
            if not task_service.runs_locally(task):
                task.assigned_node_id = None
            await task_service.record_event(
                session,
                task,
                "lease_reclaimed",
                status=TaskStatus(task.status),
                message=f"Reclaimed after lease expiry (attempt {task.retries}/{task.max_retries})",
                data={"error": error},
            )
            if task_service.runs_locally(task):
                to_enqueue.append(task)
        else:
            task.status = TaskStatus.FAILED.value
            task.completed_at = now
            task.error = error
            await task_service.record_event(
                session,
                task,
                "lease_reclaimed",
                status=TaskStatus.FAILED,
                message="Reclaimed after lease expiry; retries exhausted",
                data={"error": error},
            )
    await session.commit()
    for task in to_enqueue:
        await session.refresh(task)
    if running:
        logger.info(
            "lease reclaim sweep",
            extra={"event": "lease_sweep", "context": {"reclaimed": len(to_enqueue)}},
        )
    return to_enqueue
