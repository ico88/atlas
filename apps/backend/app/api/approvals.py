"""Approvals API — human governance gates (spec §15)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.approval import ApprovalStatus
from app.schemas.approval import ApprovalDecision, ApprovalList, ApprovalRead
from app.services import approval_service

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])


@router.get("", response_model=ApprovalList)
async def list_approvals(
    status_filter: str | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_session),
) -> ApprovalList:
    approvals = await approval_service.list_approvals(session, status=status_filter)
    return ApprovalList(
        items=[ApprovalRead.model_validate(a) for a in approvals], total=len(approvals)
    )


@router.post("/{approval_id}/approve", response_model=ApprovalRead)
async def approve(
    approval_id: str,
    decision: ApprovalDecision | None = None,
    session: AsyncSession = Depends(get_session),
) -> ApprovalRead:
    approval = await approval_service.get_approval(session, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval.status != ApprovalStatus.PENDING.value:
        raise HTTPException(status_code=409, detail="Approval already decided")
    decision = decision or ApprovalDecision()
    approval = await approval_service.approve(
        session, approval, decided_by=decision.decided_by, reason=decision.reason
    )
    return ApprovalRead.model_validate(approval)


@router.post("/{approval_id}/reject", response_model=ApprovalRead)
async def reject(
    approval_id: str,
    decision: ApprovalDecision | None = None,
    session: AsyncSession = Depends(get_session),
) -> ApprovalRead:
    approval = await approval_service.get_approval(session, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval.status != ApprovalStatus.PENDING.value:
        raise HTTPException(status_code=409, detail="Approval already decided")
    decision = decision or ApprovalDecision()
    approval = await approval_service.reject(
        session, approval, decided_by=decision.decided_by, reason=decision.reason
    )
    return ApprovalRead.model_validate(approval)
