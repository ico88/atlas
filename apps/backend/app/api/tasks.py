"""Task API (spec §15): create, read, list, cancel and event stream."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.nodes import require_node_token
from app.core.context import set_task_id
from app.db import get_session
from app.models.task import TaskStatus
from app.schemas.task import (
    TaskCreate,
    TaskEventRead,
    TaskList,
    TaskRead,
    TaskResultIn,
)
from app.services import alma_service, queue, task_service

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


async def _promote_local_dependents(session: AsyncSession, task_id: str) -> None:
    """Queue dependents that became ready; only local ones hit the Redis queue."""

    for dep in await task_service.ready_dependents(session, task_id):
        if task_service.runs_locally(dep):
            await queue.enqueue(dep.id)


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    session: AsyncSession = Depends(get_session),
) -> TaskRead:
    task = await task_service.create_task(session, payload)
    set_task_id(task.id)
    # Enqueue only local, runnable tasks. Tasks requiring a capability wait in the
    # QUEUED pool for a capable node to claim; dependency-blocked tasks are
    # enqueued later when their dependencies complete.
    if task.status == TaskStatus.QUEUED.value and task_service.runs_locally(task):
        await queue.enqueue(task.id)
    return TaskRead.model_validate(task)


@router.get("", response_model=TaskList)
async def list_tasks(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> TaskList:
    items, total = await task_service.list_tasks(
        session, status=status_filter, limit=limit, offset=offset
    )
    return TaskList(items=[TaskRead.model_validate(t) for t in items], total=total)


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(
    task_id: str,
    session: AsyncSession = Depends(get_session),
) -> TaskRead:
    task = await task_service.get_task(session, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskRead.model_validate(task)


@router.post("/{task_id}/cancel", response_model=TaskRead)
async def cancel_task(
    task_id: str,
    session: AsyncSession = Depends(get_session),
) -> TaskRead:
    task = await task_service.get_task(session, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    set_task_id(task.id)
    task = await task_service.cancel_task(session, task)
    return TaskRead.model_validate(task)


@router.post("/{task_id}/result", response_model=TaskRead)
async def report_result(
    task_id: str,
    payload: TaskResultIn,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_node_token),
) -> TaskRead:
    """A node reports the outcome of a task it executed (spec §8, remote exec)."""

    task = await task_service.get_task(session, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status not in (TaskStatus.RUNNING.value, TaskStatus.RETRYING.value):
        raise HTTPException(status_code=409, detail=f"Task not running (status={task.status})")
    set_task_id(task.id)

    if payload.status == "completed":
        task = await task_service.mark_completed(session, task, result=payload.result)
        await _promote_local_dependents(session, task.id)
    elif task.retries < task.max_retries:
        # Return to the pool for another capable node to re-claim.
        task = await task_service.requeue_remote_retry(
            session, task, error=payload.error or "remote failure"
        )
    else:
        task = await task_service.mark_failed(
            session, task, error=payload.error or "remote failure"
        )
        await alma_service.on_subtask_failed(session, task)
    return TaskRead.model_validate(task)


@router.get("/{task_id}/subtasks", response_model=list[TaskRead])
async def get_subtasks(
    task_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[TaskRead]:
    task = await task_service.get_task(session, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    subtasks = await task_service.list_subtasks(session, task_id)
    return [TaskRead.model_validate(t) for t in subtasks]


@router.get("/{task_id}/events", response_model=list[TaskEventRead])
async def get_task_events(
    task_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[TaskEventRead]:
    task = await task_service.get_task(session, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    events = await task_service.list_events(session, task_id)
    return [TaskEventRead.model_validate(e) for e in events]
