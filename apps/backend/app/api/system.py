"""System / health endpoints (spec §15)."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__, redis_client
from app.core.config import get_settings
from app.core.hardware import scan_hardware
from app.db import get_session
from app.models.approval import Approval, ApprovalStatus
from app.models.task import Task
from app.schemas.system import (
    ComponentStatus,
    HealthResponse,
    SystemMetricsResponse,
    SystemStatusResponse,
)
from app.services import node_service

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


@router.get("/api/v1/system/hardware")
async def system_hardware() -> dict:
    """Host hardware scan used to inform local model selection (spec §16 M2)."""

    return scan_hardware()


@router.get("/api/v1/system/monitor")
async def system_monitor() -> dict:
    """Live host metrics for the ATLAS Control System Monitor (SPEC §11):
    CPU, load, RAM, swap, storage, uptime, CPU temperature and GPU/VRAM.
    Real readings only — anything unavailable comes back as null (shown as N/A)."""

    from app.services import system_monitor_service

    return await system_monitor_service.snapshot(get_settings().monitor_storage_path)


@router.get("/api/v1/system/metrics", response_model=SystemMetricsResponse)
async def system_metrics(
    session: AsyncSession = Depends(get_session),
) -> SystemMetricsResponse:
    rows = await session.execute(select(Task.status, func.count()).group_by(Task.status))
    tasks_by_status = {status: int(count) for status, count in rows.all()}

    nodes = await node_service.list_nodes(session)
    nodes_online = sum(1 for n in nodes if node_service.is_online(n))

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
        nodes_total=len(nodes),
        nodes_online=nodes_online,
        approvals_pending=approvals_pending,
    )


@router.get("/api/v1/slo")
async def system_slo(session: AsyncSession = Depends(get_session)) -> dict:
    """Service-level objectives + advisory alerts (ROADMAP R5)."""

    from app.services import slo_service

    # Redis reachability stands in for control-plane health here.
    healthy = True
    try:
        await redis_client.get_redis().ping()
    except Exception:  # noqa: BLE001 - unreachable Redis => unhealthy SLO
        healthy = False
    return await slo_service.report(session, healthy=healthy)


@router.get("/api/v1/logs")
async def logs_list(
    filter: str = "",
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """Control plane logs (C/1). Mock sample entries; TODO: wire to actual logging.

    Query params:
      filter: substring match on message or level (e.g. "error", "deepseek")
      limit: max entries to return (default 100)
      offset: pagination offset (default 0)
    """
    # Mock log entries (in a real system, these would come from a log aggregator)
    sample_logs = [
        {
            "timestamp": "2026-09-26T18:15:42Z",
            "level": "INFO",
            "source": "backend",
            "message": "DeepSeek V4 Flash loaded successfully on node-1",
        },
        {
            "timestamp": "2026-09-26T18:14:18Z",
            "level": "INFO",
            "source": "llama.cpp",
            "message": "Inference complete: 512 tokens in 4.2s (121.9 t/s)",
        },
        {
            "timestamp": "2026-09-26T18:10:05Z",
            "level": "WARN",
            "source": "node-agent",
            "message": "Memory usage approaching limit: 3.2GB / 3.5GB",
        },
        {
            "timestamp": "2026-09-26T18:05:33Z",
            "level": "INFO",
            "source": "backend",
            "message": "Autopilot experiment started: model_swap_candidate",
        },
        {
            "timestamp": "2026-09-26T18:00:00Z",
            "level": "ERROR",
            "source": "llama.cpp",
            "message": "GGUF load failed: insufficient context size",
        },
    ]

    # Filter
    if filter:
        sample_logs = [
            log
            for log in sample_logs
            if filter.lower() in log["message"].lower()
            or filter.lower() in log["level"].lower()
        ]

    # Paginate
    total = len(sample_logs)
    items = sample_logs[offset : offset + limit]

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/api/v1/agents")
async def agents_list(
    session: AsyncSession = Depends(get_session),
) -> dict:
    """List autonomous agents running on nodes (C/1).

    Returns: { nodes: [ { id, state, agents: [ { name, status, task } ] } ] }
    """
    nodes = await node_service.list_nodes(session)

    # Mock agent data per node
    agent_data = {
        "node-1": [
            {"name": "improve-model", "status": "running", "task": "A/B experiment on DeepSeek"},
            {"name": "monitor-health", "status": "idle", "task": "system health checks"},
        ],
        "node-2": [
            {"name": "cache-manager", "status": "running", "task": "optimize KV cache"},
        ],
    }

    return {
        "nodes": [
            {
                "id": n.id,
                "state": "UP" if node_service.is_online(n) else "DOWN",
                "agents": agent_data.get(n.id, []),
            }
            for n in nodes
        ]
    }
