"""Human approval gates (spec §14: approvals, §11 step 12)."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import Approval, ApprovalStatus
from app.models.base import utcnow
from app.models.maintenance import (
    IssueStatus,
    MaintenanceIssue,
    MaintenanceRun,
    RunStatus,
)

logger = logging.getLogger(__name__)


async def list_approvals(
    session: AsyncSession, *, status: str | None = None
) -> list[Approval]:
    query = select(Approval).order_by(Approval.created_at.desc())
    if status:
        query = query.where(Approval.status == status)
    return list((await session.execute(query)).scalars().all())


async def get_approval(session: AsyncSession, approval_id: str) -> Approval | None:
    return await session.get(Approval, approval_id)


async def _apply_maintenance_decision(
    session: AsyncSession, approval: Approval, approved: bool
) -> None:
    """Reflect an approval decision on the linked maintenance run/issue."""

    if approval.subject_type != "maintenance_run" or not approval.subject_id:
        return
    run = await session.get(MaintenanceRun, approval.subject_id)
    if run is None:
        return
    run.status = RunStatus.APPROVED.value if approved else RunStatus.REJECTED.value
    # Fetch the issue explicitly (never touch the lazy relationship under async).
    issue = await session.get(MaintenanceIssue, run.issue_id)
    if issue is not None:
        # Approved => the human accepted the fix (they merge it themselves, §11.2).
        issue.status = IssueStatus.RESOLVED.value if approved else IssueStatus.OPEN.value


async def approve(
    session: AsyncSession, approval: Approval, *, decided_by: str, reason: str | None = None
) -> Approval:
    approval.status = ApprovalStatus.APPROVED.value
    approval.decided_by = decided_by
    approval.decided_at = utcnow()
    if reason:
        approval.reason = reason
    await _apply_maintenance_decision(session, approval, approved=True)
    await session.commit()
    await session.refresh(approval)
    logger.info(
        "approval granted",
        extra={"event": "approval_granted", "context": {"approval_id": approval.id}},
    )
    return approval


async def reject(
    session: AsyncSession, approval: Approval, *, decided_by: str, reason: str | None = None
) -> Approval:
    approval.status = ApprovalStatus.REJECTED.value
    approval.decided_by = decided_by
    approval.decided_at = utcnow()
    if reason:
        approval.reason = reason
    await _apply_maintenance_decision(session, approval, approved=False)
    await session.commit()
    await session.refresh(approval)
    logger.info(
        "approval rejected",
        extra={"event": "approval_rejected", "context": {"approval_id": approval.id}},
    )
    return approval
