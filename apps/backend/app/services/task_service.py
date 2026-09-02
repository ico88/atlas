"""Task persistence, state transitions and event recording (spec §7).

All state changes go through this service so that every transition also writes a
``task_events`` row -- the audit trail that lets a task's history survive a
backend restart (Sprint 1 acceptance criterion).
"""

from __future__ import annotations

import logging
import random
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.base import utcnow
from app.models.task import Task, TaskDependency, TaskEvent, TaskStatus
from app.schemas.task import TaskCreate

logger = logging.getLogger(__name__)


def compute_backoff(attempt: int) -> float:
    """Exponential backoff with jitter (spec §7). ``attempt`` starts at 1."""

    settings = get_settings()
    base = settings.retry_backoff_base * (2 ** max(0, attempt - 1))
    delay = min(base, settings.retry_backoff_max)
    return delay + random.uniform(0, settings.retry_jitter)


async def record_event(
    session: AsyncSession,
    task: Task,
    event_type: str,
    *,
    status: TaskStatus | None = None,
    message: str | None = None,
    data: dict[str, Any] | None = None,
) -> TaskEvent:
    """Append an event to a task's history. Does not commit."""

    event = TaskEvent(
        task_id=task.id,
        event_type=event_type,
        status=status.value if status else None,
        message=message,
        data=data,
    )
    session.add(event)
    return event


async def get_by_idempotency_key(session: AsyncSession, key: str) -> Task | None:
    result = await session.execute(select(Task).where(Task.idempotency_key == key))
    return result.scalars().first()


async def create_task(session: AsyncSession, data: TaskCreate) -> Task:
    """Create a task and record the ``created`` event.

    Honors idempotency (returns the existing task for a repeated key), records
    declared dependencies, and starts a task in WAITING_DEPENDENCY when any of
    its dependencies has not completed yet (otherwise QUEUED). The caller is
    responsible for enqueuing the task only when it is QUEUED.
    """

    if data.idempotency_key:
        existing = await get_by_idempotency_key(session, data.idempotency_key)
        if existing is not None:
            return existing

    settings = get_settings()
    max_retries = data.max_retries if data.max_retries is not None else settings.task_max_retries
    task = Task(
        title=data.title,
        objective=data.objective,
        type=data.type,
        priority=data.priority,
        payload=data.payload,
        owner_id=data.owner_id,
        parent_task_id=data.parent_task_id,
        idempotency_key=data.idempotency_key,
        max_retries=max_retries,
        status=TaskStatus.QUEUED.value,
    )
    if data.correlation_id:
        task.correlation_id = data.correlation_id
    session.add(task)
    await session.flush()  # assign task.id / defaults

    depends_on = data.depends_on or []
    for dep_id in depends_on:
        session.add(TaskDependency(task_id=task.id, depends_on_task_id=dep_id))
    await session.flush()

    if depends_on and await unmet_dependencies(session, task.id):
        task.status = TaskStatus.WAITING_DEPENDENCY.value
        await record_event(
            session,
            task,
            "created",
            status=TaskStatus.WAITING_DEPENDENCY,
            message="Task created, waiting on dependencies",
        )
    else:
        await record_event(
            session, task, "created", status=TaskStatus.QUEUED, message="Task created"
        )
    await session.commit()
    await session.refresh(task)
    logger.info(
        "task created",
        extra={"event": "task_created", "context": {"task_id": task.id, "type": task.type}},
    )
    return task


async def unmet_dependencies(session: AsyncSession, task_id: str) -> list[str]:
    """Return dependency task ids that have not COMPLETED yet."""

    dep_ids = list(
        (
            await session.execute(
                select(TaskDependency.depends_on_task_id).where(
                    TaskDependency.task_id == task_id
                )
            )
        )
        .scalars()
        .all()
    )
    unmet: list[str] = []
    for dep_id in dep_ids:
        dep = await session.get(Task, dep_id)
        if dep is None or dep.status != TaskStatus.COMPLETED.value:
            unmet.append(dep_id)
    return unmet


async def ready_dependents(session: AsyncSession, completed_task_id: str) -> list[Task]:
    """Move dependents whose dependencies are now all met to QUEUED.

    Returns the tasks that became QUEUED so the caller can enqueue them.
    """

    dependent_ids = list(
        (
            await session.execute(
                select(TaskDependency.task_id).where(
                    TaskDependency.depends_on_task_id == completed_task_id
                )
            )
        )
        .scalars()
        .all()
    )
    promoted: list[Task] = []
    for dep_task_id in dependent_ids:
        task = await session.get(Task, dep_task_id)
        if task is None or task.status != TaskStatus.WAITING_DEPENDENCY.value:
            continue
        if await unmet_dependencies(session, task.id):
            continue
        task.status = TaskStatus.QUEUED.value
        await record_event(
            session,
            task,
            "status_changed",
            status=TaskStatus.QUEUED,
            message="Dependencies satisfied; queued",
        )
        promoted.append(task)
    if promoted:
        await session.commit()
        for task in promoted:
            await session.refresh(task)
    return promoted


async def get_task(session: AsyncSession, task_id: str) -> Task | None:
    return await session.get(Task, task_id)


async def list_tasks(
    session: AsyncSession,
    *,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Task], int]:
    query = select(Task)
    count_query = select(func.count()).select_from(Task)
    if status:
        query = query.where(Task.status == status)
        count_query = count_query.where(Task.status == status)

    query = query.order_by(Task.created_at.desc()).limit(limit).offset(offset)
    items = list((await session.execute(query)).scalars().all())
    total = int((await session.execute(count_query)).scalar_one())
    return items, total


async def list_events(session: AsyncSession, task_id: str) -> list[TaskEvent]:
    query = (
        select(TaskEvent)
        .where(TaskEvent.task_id == task_id)
        .order_by(TaskEvent.created_at.asc(), TaskEvent.id.asc())
    )
    return list((await session.execute(query)).scalars().all())


async def cancel_task(session: AsyncSession, task: Task) -> Task:
    """Logically cancel a task if it has not reached a terminal state."""

    current = TaskStatus(task.status)
    if current.is_terminal:
        return task
    task.status = TaskStatus.CANCELLED.value
    task.completed_at = utcnow()
    await record_event(
        session,
        task,
        "status_changed",
        status=TaskStatus.CANCELLED,
        message="Task cancelled by request",
    )
    await session.commit()
    await session.refresh(task)
    logger.info(
        "task cancelled",
        extra={"event": "task_cancelled", "context": {"task_id": task.id}},
    )
    return task


async def mark_running(session: AsyncSession, task: Task) -> Task:
    task.status = TaskStatus.RUNNING.value
    task.started_at = utcnow()
    await record_event(
        session, task, "status_changed", status=TaskStatus.RUNNING, message="Task started"
    )
    await session.commit()
    await session.refresh(task)
    return task


async def mark_completed(
    session: AsyncSession, task: Task, result: dict[str, Any] | None = None
) -> Task:
    task.status = TaskStatus.COMPLETED.value
    task.completed_at = utcnow()
    task.result = result
    await record_event(
        session,
        task,
        "status_changed",
        status=TaskStatus.COMPLETED,
        message="Task completed",
        data=result,
    )
    await session.commit()
    await session.refresh(task)
    return task


async def mark_failed(session: AsyncSession, task: Task, error: str) -> Task:
    task.status = TaskStatus.FAILED.value
    task.completed_at = utcnow()
    task.error = error
    await record_event(
        session,
        task,
        "status_changed",
        status=TaskStatus.FAILED,
        message="Task failed",
        data={"error": error},
    )
    await session.commit()
    await session.refresh(task)
    return task


async def schedule_retry(session: AsyncSession, task: Task, error: str) -> float:
    """Mark a task RETRYING, bump the attempt count, and return the backoff delay."""

    task.retries += 1
    task.status = TaskStatus.RETRYING.value
    task.error = error
    delay = compute_backoff(task.retries)
    await record_event(
        session,
        task,
        "status_changed",
        status=TaskStatus.RETRYING,
        message=f"Retry {task.retries}/{task.max_retries} scheduled",
        data={"error": error, "delay_seconds": round(delay, 3)},
    )
    await session.commit()
    await session.refresh(task)
    return delay
