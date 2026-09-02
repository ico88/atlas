"""Chat / conversation schemas (spec §15)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.conversation import ChatMode


class ChatRequest(BaseModel):
    content: str = Field(min_length=1)
    conversation_id: str | None = None
    model: str | None = None
    mode: ChatMode = ChatMode.AUTO


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    role: str
    content: str
    model: str | None
    provider: str | None
    latency_ms: int | None
    created_at: datetime


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str | None
    mode: str
    created_at: datetime
    updated_at: datetime


class ConversationRead(ConversationSummary):
    messages: list[MessageRead] = []


class ConversationList(BaseModel):
    items: list[ConversationSummary]
    total: int
