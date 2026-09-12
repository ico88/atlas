"""Autopilot API — one read-only summary of ATLAS's autonomous activity."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.services import autopilot_service

router = APIRouter(prefix="/api/v1/autopilot", tags=["autopilot"])


@router.get("")
async def get_autopilot(
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await autopilot_service.summary(session, limit=limit)
