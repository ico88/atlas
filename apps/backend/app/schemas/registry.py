"""Model registry schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ModelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    name: str
    model_key: str | None = None
    family: str | None
    parameter_count: str | None = None
    quantization: str | None = None
    format: str | None = None
    context_length: int | None
    capabilities: dict[str, Any] | None
    available: bool
    updated_at: datetime


class ModelList(BaseModel):
    items: list[ModelRead]
    total: int
