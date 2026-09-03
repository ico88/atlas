"""Environment schemas (ROADMAP PR 13)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EnvironmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    manifest: dict[str, Any] | None = None
    variables: dict[str, Any] | None = None


class EnvironmentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    manifest: dict[str, Any] | None = None
    variables: dict[str, Any] | None = None
    status: str | None = Field(default=None, pattern="^(ACTIVE|ARCHIVED)$")


class EnvironmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    name: str
    description: str | None
    status: str
    manifest: dict[str, Any] | None
    variables: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class EnvironmentList(BaseModel):
    items: list[EnvironmentRead]
    total: int


class SnapshotCreate(BaseModel):
    name: str | None = None
    created_by: str | None = None


class SnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    environment_id: str
    name: str | None
    manifest: dict[str, Any] | None
    variables: dict[str, Any] | None
    stats: dict[str, Any] | None
    created_by: str | None
    created_at: datetime


class SnapshotList(BaseModel):
    items: list[SnapshotRead]
    total: int
