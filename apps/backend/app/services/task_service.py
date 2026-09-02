"""Task persistence, state transitions and event recording (spec §7).

All state changes go through this service so that every transition also writes a
``task_events`` row -- the audit trail that lets a task's history survive a
backend restart (Sprint 1 acceptance criterion).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utcnow
from app.models.task import Task, TaskEvent, TaskStatus
from app.schemas.task import TaskCreate

logger = logging.getLogger(__name__)


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


async def create_task(session: AsyncSession, data: TaskCreate) -> Task:
    """Create a QUEUED task and record the ``created`` event."""

    task = Task(
        title=data.title,
        objective=data.objective,
        type=data.type,
        priority=data.priority,
        payload=data.payload,
        owner_id=data.owner_id,
        parent_task_id=data.parent_task_id,
        status=TaskStatus.QUEUED.value,
    )
    if data.correlation_id:
        task.correlation_id = data.correlation_id
    session.add(task)
    await session.flush()  # assign task.id / defaults

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
