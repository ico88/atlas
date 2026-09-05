"""Control-plane cluster / HA status API (ROADMAP PR 9)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.services import leadership_service

router = APIRouter(prefix="/api/v1/cluster", tags=["cluster"])


@router.get("")
async def cluster_status() -> dict[str, Any]:
    """Cluster members, the current leader, and whether HA is enabled."""

    return await leadership_service.cluster_status()
