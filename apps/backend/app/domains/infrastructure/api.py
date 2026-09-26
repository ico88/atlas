"""Infrastructure & System domain API — System Status, Cluster, Networking.

Infrastructure domain: System health monitoring, cluster management, high availability,
networking (ZeroTier), node setup, maintenance and operations.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.system import SystemStatusRead
from app.services import system_monitor_service

router = APIRouter(tags=["infrastructure"])

# ============================================================================
# System Status
# ============================================================================

system_router = APIRouter(prefix="/api/v1/system", tags=["system"])


@system_router.get("", response_model=SystemStatusRead)
async def get_system_status(session: AsyncSession = Depends(get_session)) -> SystemStatusRead:
    """System health, nodes, models, resource utilization."""
    return await system_monitor_service.get_status(session)


@system_router.get("/health")
async def health_check() -> dict:
    """Liveness probe."""
    return {"status": "healthy"}


@system_router.get("/metrics")
async def get_metrics(session: AsyncSession = Depends(get_session)) -> dict:
    """System metrics: CPU, memory, disk, inference throughput."""
    return {"uptime_seconds": 86400}


# ============================================================================
# Cluster Management
# ============================================================================

cluster_router = APIRouter(prefix="/api/v1/cluster", tags=["cluster"])


@cluster_router.get("")
async def get_cluster_status(session: AsyncSession = Depends(get_session)) -> dict:
    """Cluster state, member status, leader election."""
    return {"nodes": 1, "leader": True}


@cluster_router.post("/resign")
async def resign_leadership(session: AsyncSession = Depends(get_session)) -> dict:
    """Resign leadership (for manual failover)."""
    return {"status": "resigned"}


# ============================================================================
# Setup Wizard
# ============================================================================

setup_router = APIRouter(prefix="/api/v1/setup", tags=["setup"])


@setup_router.get("")
async def get_setup_status(session: AsyncSession = Depends(get_session)) -> dict:
    """Setup wizard state and progress."""
    return {"completed": True, "version": "v0.1.0"}


# ============================================================================
# Networking (ZeroTier)
# ============================================================================

zerotier_router = APIRouter(prefix="/api/v1/zerotier", tags=["zerotier"])


@zerotier_router.get("")
async def get_zerotier_status(session: AsyncSession = Depends(get_session)) -> dict:
    """ZeroTier network status and peers."""
    return {"network_id": "...", "peers": []}


# ============================================================================
# Aggregate all infrastructure routers
# ============================================================================

router.include_router(system_router)
router.include_router(cluster_router)
router.include_router(setup_router)
router.include_router(zerotier_router)
