"""Fleet deployment API schemas (ROADMAP PR 21 / PR 22)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DeploymentCreate(BaseModel):
    target_version: str = Field(min_length=1, max_length=64)
    canary_count: int = Field(default=1, ge=0, le=1000)
    min_compatible: str | None = None
    note: str | None = None


class ReportRequest(BaseModel):
    node_ref: str
    version: str
    healthy: bool = True


class TargetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    node_ref: str
    from_version: str | None
    wave: str
    status: str
    detail: str | None


class DeploymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    target_version: str
    previous_version: str | None
    strategy: str
    canary_count: int
    status: str
    note: str | None
    created_at: datetime
    updated_at: datetime
    targets: list[TargetRead] = []


class DeploymentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    target_version: str
    status: str
    canary_count: int
    created_at: datetime


class DeploymentList(BaseModel):
    items: list[DeploymentSummary]
    total: int
