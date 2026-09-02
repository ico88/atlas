"""Conversation queue schemas (ROADMAP PR 11)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EnqueueRequest(BaseModel):
    content: str = Field(min_length=1)
    role: str = "user"
    merge: bool = True


class EnqueueResponse(BaseModel):
    status: str  # "dispatched" | "queued"
    conversation_id: str
    pending: int
    position: int | None = None
    message: dict[str, Any] | None = None


class QueueStatusResponse(BaseModel):
    conversation_id: str
    active: bool
    pending: int
    items: list[dict[str, Any]]
    active_total: int


class CompleteResponse(BaseModel):
    conversation_id: str
    next: dict[str, Any] | None = None
