"""System / health endpoints (spec §15)."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__, redis_client
from app.core.config import get_settings
from app.db import get_session
from app.models.approval import Approval, ApprovalStatus
from app.models.node import Node
from app.models.task import Task
from app.schemas.system import (
    ComponentStatus,
    HealthResponse,
    SystemMetricsResponse,
    SystemStatusResponse,
)

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness probe -- returns healthy if the process is serving requests."""

    return HealthResponse(status="healthy", version=__version__)


async def _check_database(session: AsyncSession) -> ComponentStatus:
    start = time.perf_counter()
    try:
        await session.execute(select(1))
        latency = round((time.perf_counter() - start) * 1000, 2)
        return ComponentStatus(name="database", status="healthy", latency_ms=latency)
    except Exception as exc:  # noqa: BLE001 - report any connectivity failure
        return ComponentStatus(name="database", status="unhealthy", detail=str(exc))


async def _check_redis() -> ComponentStatus:
    start = time.perf_counter()
    try:
        await redis_client.get_redis().ping()
        latency = round((time.perf_counter() - start) * 1000, 2)
        return ComponentStatus(name="redis", status="healthy", latency_ms=latency)
    except Exception as exc:  # noqa: BLE001
        return ComponentStatus(name="redis", status="unhealthy", detail=str(exc))


@router.get("/api/v1/system/status", response_model=SystemStatusResponse)
async def system_status(
    session: AsyncSession = Depends(get_session),
) -> SystemStatusResponse:
    """Readiness view consumed by the frontend System Status page."""

    settings = get_settings()
    backend = ComponentStatus(name="backend", status="healthy")
    components = [backend, await _check_database(session), await _check_redis()]
    overall = "healthy" if all(c.status == "healthy" for c in components) else "degraded"
    return SystemStatusResponse(
        status=overall,
        version=__version__,
        environment=settings.env,
        components=components,
    )


@router.get("/api/v1/system/metrics", response_model=SystemMetricsResponse)
async def system_metrics(
    session: AsyncSession = Depends(get_session),
) -> SystemMetricsResponse:
    rows = await session.execute(select(Task.status, func.count()).group_by(Task.status))
    tasks_by_status = {status: int(count) for status, count in rows.all()}

    nodes_online = int(
        (
            await session.execute(
                select(func.count()).select_from(Node).where(Node.status == "online")
            )
        ).scalar_one()
    )
    approvals_pending = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Approval)
                .where(Approval.status == ApprovalStatus.PENDING.value)
            )
        ).scalar_one()
    )
    return SystemMetricsResponse(
        tasks_by_status=tasks_by_status,
        nodes_online=nodes_online,
        approvals_pending=approvals_pending,
    )
