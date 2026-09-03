"""Resource telemetry API (ROADMAP PR 12)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.metrics import (
    NodeMetricList,
    NodeMetricRead,
    OllamaPerfResponse,
    OllamaPerfRow,
)
from app.services import metrics_service

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])


@router.get("/nodes", response_model=list[NodeMetricRead])
async def latest_node_metrics(
    session: AsyncSession = Depends(get_session),
) -> list[NodeMetricRead]:
    """The most recent telemetry sample for each node."""

    rows = await metrics_service.latest_per_node(session)
    return [NodeMetricRead.model_validate(m) for m in rows]


@router.get("/nodes/{node_id}", response_model=NodeMetricList)
async def node_metric_history(
    node_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
) -> NodeMetricList:
    rows = await metrics_service.history(session, node_id, limit=limit)
    return NodeMetricList(
        node_id=node_id,
        items=[NodeMetricRead.model_validate(m) for m in rows],
        total=len(rows),
    )


@router.get("/ollama", response_model=OllamaPerfResponse)
async def ollama_performance(
    session: AsyncSession = Depends(get_session),
) -> OllamaPerfResponse:
    rows = await metrics_service.ollama_perf(session)
    return OllamaPerfResponse(items=[OllamaPerfRow(**r) for r in rows])
