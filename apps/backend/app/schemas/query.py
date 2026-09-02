"""Query lifecycle schemas (ROADMAP PR 10)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.conversation import ChatMode


class QueryCreate(BaseModel):
    prompt: str = Field(min_length=1)
    conversation_id: str | None = None
    model: str | None = None
    mode: ChatMode = ChatMode.AUTO


class QueryEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_type: str
    status: str | None
    message: str | None
    created_at: datetime


class QueryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str | None
    prompt: str
    mode: str
    model: str | None
    provider: str | None
    status: str
    result: str | None
    error: str | None
    cancel_requested: bool
    progress: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class QueryDetail(QueryRead):
    events: list[QueryEventRead] = []


class QueryList(BaseModel):
    items: list[QueryRead]
    total: int
