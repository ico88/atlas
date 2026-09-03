"""RAG / memory / feedback API schemas (spec §6, §14, M8)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None


class KnowledgeBaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    created_at: datetime


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    kb_id: str | None = None
    source: str | None = None
    content_type: str = "text/plain"
    metadata: dict[str, Any] | None = None


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kb_id: str | None
    title: str
    source: str | None
    content_type: str
    created_at: datetime


class DocumentList(BaseModel):
    items: list[DocumentRead]
    total: int


class RagQuery(BaseModel):
    query: str = Field(min_length=1)
    kb_id: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=50)


class Citation(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    source: str | None
    chunk_index: int
    content: str
    score: float


class RagResult(BaseModel):
    query: str
    hits: list[Citation]


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1)
    scope: str = "user"
    scope_id: str | None = None
    environment_id: str | None = None
    source: str | None = None
    source_id: str | None = None
    mem_type: str = "fact"
    tags: list[str] | None = None
    importance: int = Field(default=0, ge=0, le=100)
    pinned: bool = False
    ttl_seconds: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] | None = None


class MemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    content: str
    scope: str
    scope_id: str | None
    environment_id: str | None = None
    source: str | None = None
    source_id: str | None = None
    mem_type: str = "fact"
    tags: list[str] | None = None
    importance: int = 0
    pinned: bool = False
    expires_at: datetime | None = None
    last_accessed_at: datetime | None = None
    access_count: int = 0
    created_at: datetime


class MemorySearch(BaseModel):
    query: str = Field(min_length=1)
    scope: str | None = None
    scope_id: str | None = None
    environment_id: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=50)


class MemoryHitRead(BaseModel):
    id: str
    content: str
    scope: str
    scope_id: str | None
    score: float
    source: str | None = None
    mem_type: str = "fact"
    tags: list[str] | None = None
    importance: int = 0
    pinned: bool = False


class MemoryImportanceUpdate(BaseModel):
    importance: int = Field(ge=0, le=100)


class MemoryPinUpdate(BaseModel):
    pinned: bool


class FeedbackCreate(BaseModel):
    target_type: str = Field(min_length=1, max_length=32)
    target_id: str = Field(min_length=1)
    rating: int = Field(default=0, ge=-1, le=1)
    comment: str | None = None
    user_id: str | None = None


class FeedbackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    target_type: str
    target_id: str
    rating: int
    comment: str | None
    user_id: str | None
    created_at: datetime
