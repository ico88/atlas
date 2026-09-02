"""Pydantic schemas for system/health endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class ComponentStatus(BaseModel):
    name: str
    status: str  # "healthy" | "unhealthy"
    detail: str | None = None
    latency_ms: float | None = None


class HealthResponse(BaseModel):
    status: str
    version: str


class SystemStatusResponse(BaseModel):
    status: str  # overall: "healthy" | "degraded"
    version: str
    environment: str
    components: list[ComponentStatus]


class SystemMetricsResponse(BaseModel):
    tasks_by_status: dict[str, int]
    nodes_total: int
    nodes_online: int
    approvals_pending: int
