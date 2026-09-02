"""Task API (spec §15): create, read, list, cancel and event stream."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import set_task_id
from app.db import get_session
from app.models.task import TaskStatus
from app.schemas.task import TaskCreate, TaskEventRead, TaskList, TaskRead
from app.services import queue, task_service

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    session: AsyncSession = Depends(get_session),
) -> TaskRead:
    task = await task_service.create_task(session, payload)
    set_task_id(task.id)
    # Enqueue only when actually runnable. Tasks waiting on dependencies are
    # enqueued later, when their dependencies complete. Persistence already
    # happened, so a transient enqueue failure does not lose the task.
    if task.status == TaskStatus.QUEUED.value:
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
