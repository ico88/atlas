"""Resource telemetry schemas (ROADMAP PR 12)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class NodeMetricRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    node_id: str
    load1: float | None
    ram_free_mb: int | None
    data: dict[str, Any] | None
    created_at: datetime


class NodeMetricList(BaseModel):
    node_id: str
    items: list[NodeMetricRead]
    total: int


class OllamaPerfRow(BaseModel):
    provider: str | None
    model: str | None
    count: int
    avg_latency_ms: float | None
    min_latency_ms: int | None
    max_latency_ms: int | None


class OllamaPerfResponse(BaseModel):
    items: list[OllamaPerfRow]
