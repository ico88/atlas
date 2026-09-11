"""Local fine-tuning API schemas (ROADMAP self-improvement)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    base_model: str | None = None


class DatasetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    base_model: str | None
    created_at: datetime
    updated_at: datetime


class DatasetList(BaseModel):
    items: list[DatasetRead]
    total: int


class ExampleCreate(BaseModel):
    prompt: str = Field(min_length=1)
    response: str = Field(min_length=1)
    system_prompt: str | None = None
    quality: float = 1.0


class ExampleIncluded(BaseModel):
    included: bool


class ExampleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    dataset_id: str
    system_prompt: str | None
    prompt: str
    response: str
    source: str
    source_id: str | None
    quality: float
    included: bool
    created_at: datetime


class ExampleList(BaseModel):
    items: list[ExampleRead]
    total: int


class CurateRequest(BaseModel):
    min_rating: int = Field(default=1, ge=1)


class CurateResult(BaseModel):
    added: int


class JobCreate(BaseModel):
    dataset_id: str
    base_model: str | None = None
    adapter_name: str | None = None
    hyperparams: dict[str, Any] | None = None


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    dataset_id: str
    base_model: str
    adapter_name: str
    method: str
    status: str
    task_id: str | None
    example_count: int
    hyperparams: dict[str, Any] | None
    metrics: dict[str, Any] | None
    output: dict[str, Any] | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class JobList(BaseModel):
    items: list[JobRead]
    total: int


class Readiness(BaseModel):
    gpu_node_available: bool
    gpu_node_names: list[str]
    positive_feedback: int
    recommended_min_examples: int
