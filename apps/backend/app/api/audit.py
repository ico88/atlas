"""Append-only audit trail API (ROADMAP R5).

Read-only: the log can be listed and its integrity verified, but never edited or
deleted through the API. When RBAC is enforced these are admin-only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db import get_session
from app.services import audit_service

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


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


@router.get("", response_model=AuditList, dependencies=[Depends(require_admin)])
async def list_audit(
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
) -> AuditList:
    entries = await audit_service.list_entries(session, limit=limit)
    total = await audit_service.count(session)
    return AuditList(items=[AuditEntryRead.model_validate(e) for e in entries], total=total)


@router.get("/verify", dependencies=[Depends(require_admin)])
async def verify_audit(session: AsyncSession = Depends(get_session)) -> dict:
    return await audit_service.verify_chain(session)
