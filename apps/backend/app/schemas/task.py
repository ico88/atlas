"""Pydantic schemas for the Task API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.task import TaskStatus


class TaskCreate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    objective: str | None = None
    type: str = Field(default="dummy", max_length=64)
    priority: int = 0
    payload: dict[str, Any] | None = None
    owner_id: str | None = None
    parent_task_id: str | None = None
    correlation_id: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)
    max_retries: int | None = Field(default=None, ge=0, le=20)
    depends_on: list[str] | None = None
    required_capability: str | None = Field(default=None, max_length=64)


class TaskEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    event_type: str
    status: str | None
    message: str | None
    data: dict[str, Any] | None
    created_at: datetime


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str | None
    title: str | None
    objective: str | None
    type: str
    status: TaskStatus
    priority: int
    payload: dict[str, Any] | None
    result: dict[str, Any] | None
    error: str | None
    retries: int
    max_retries: int
    idempotency_key: str | None
    required_capability: str | None
    assigned_node_id: str | None
    parent_task_id: str | None
    correlation_id: str
    deadline: datetime | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class TaskList(BaseModel):
    items: list[TaskRead]
    total: int


class TaskResultIn(BaseModel):
    """Result reported by a node after executing a claimed task."""

    status: str = Field(pattern="^(completed|failed)$")
    result: dict[str, Any] | None = None
    error: str | None = None
