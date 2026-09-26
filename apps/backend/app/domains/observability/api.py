"""Observability & Monitoring domain API — Audit, Metrics, Logs.

Observability domain: System monitoring, metrics collection, audit logging, trace collection,
alert management, and operational visibility.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db import get_session
from app.schemas.metrics import (
    NodeMetricList,
    NodeMetricRead,
    OllamaPerfResponse,
    OllamaPerfRow,
)
from app.domains.observability import audit, metrics

router = APIRouter(tags=["observability"])

# ============================================================================
# Audit
# ============================================================================

audit_router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


class AuditEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    actor: str
    action: str
    target: str | None
    detail: dict[str, Any] | None
    hash: str
    created_at: datetime


class AuditList(BaseModel):
    items: list[AuditEntryRead]
    total: int


@audit_router.get("", response_model=AuditList, dependencies=[Depends(require_admin)])
async def list_audit(
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
) -> AuditList:
    entries = await audit.list_entries(session, limit=limit)
    total = await audit.count(session)
    return AuditList(items=[AuditEntryRead.model_validate(e) for e in entries], total=total)


@audit_router.get("/verify", dependencies=[Depends(require_admin)])
async def verify_audit(session: AsyncSession = Depends(get_session)) -> dict:
    return await audit.verify_chain(session)


# ============================================================================
# Metrics
# ============================================================================

metrics_router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])


@metrics_router.get("/nodes", response_model=list[NodeMetricRead])
async def latest_node_metrics(
    session: AsyncSession = Depends(get_session),
) -> list[NodeMetricRead]:
    """The most recent telemetry sample for each node."""

    rows = await metrics.latest_per_node(session)
    return [NodeMetricRead.model_validate(m) for m in rows]


@metrics_router.get("/nodes/{node_id}", response_model=NodeMetricList)
async def node_metric_history(
    node_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
) -> NodeMetricList:
    rows = await metrics.history(session, node_id, limit=limit)
    return NodeMetricList(
        node_id=node_id,
        items=[NodeMetricRead.model_validate(m) for m in rows],
        total=len(rows),
    )


@metrics_router.get("/ollama", response_model=OllamaPerfResponse)
async def ollama_performance(
    session: AsyncSession = Depends(get_session),
) -> OllamaPerfResponse:
    rows = await metrics.ollama_perf(session)
    return OllamaPerfResponse(items=[OllamaPerfRow(**r) for r in rows])


# ============================================================================
# Aggregate all observability routers
# ============================================================================

router.include_router(audit_router)
router.include_router(metrics_router)
