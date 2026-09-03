"""Chat / conversation schemas (spec §15)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.conversation import ChatMode


class ChatRequest(BaseModel):
    content: str = Field(min_length=1)
    conversation_id: str | None = None
    model: str | None = None
    mode: ChatMode = ChatMode.AUTO
    web: bool = False  # ground the reply with a web search (ROADMAP PR 15)


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    role: str
    content: str
    status: str = "complete"
    model: str | None
    provider: str | None
    latency_ms: int | None
    citations: list[Any] | None = None
    created_at: datetime


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str | None
    mode: str
    archived: bool = False
    created_at: datetime
    updated_at: datetime


class ConversationRead(ConversationSummary):
    messages: list[MessageRead] = []


class ConversationList(BaseModel):
    items: list[ConversationSummary]
    total: int
