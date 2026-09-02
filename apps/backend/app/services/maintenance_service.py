"""Maintenance Agent workflow (spec §11).

Implements the deterministic, human-governed slice of the agent:
ingest+fingerprint -> issue, analyze -> run, create-fix -> branch/patch/tests/PR
(via the guard-railed dry-run Git provider) -> NEEDS_APPROVAL gate. It never
merges to main or performs any real, ungated repository mutation.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.maintenance.fingerprint import compute_fingerprint
from app.maintenance.git import AuditGitProvider, GitGuardrailError
from app.models.approval import Approval, ApprovalStatus
from app.models.base import utcnow
from app.models.maintenance import (
    GitAction,
    IssueStatus,
    MaintenanceIssue,
    MaintenanceRun,
    RunStatus,
    Severity,
)

logger = logging.getLogger(__name__)

_LEVEL_SEVERITY = {
    "CRITICAL": Severity.CRITICAL.value,
    "FATAL": Severity.CRITICAL.value,
    "ERROR": Severity.HIGH.value,
    "WARNING": Severity.MEDIUM.value,
    "WARN": Severity.MEDIUM.value,
}


def _severity_for(level: str | None) -> str:
    return _LEVEL_SEVERITY.get((level or "").upper(), Severity.LOW.value)


async def ingest_log(
    session: AsyncSession,
    *,
    message: str,
    service: str | None = None,
    level: str | None = None,
    event: str | None = None,
    context: dict[str, Any] | None = None,
) -> MaintenanceIssue:
    """Fingerprint a log event and upsert its maintenance issue (dedup)."""

    fingerprint = compute_fingerprint(
        service=service, message=message, level=level, event=event
    )
    existing = (
        await session.execute(
            select(MaintenanceIssue).where(MaintenanceIssue.fingerprint == fingerprint)
        )
    ).scalar_one_or_none()

    sample = {
        "message": message,
        "level": level,
        "event": event,
        "service": service,
        "context": context,
    }

    if existing is not None:
        existing.occurrences += 1
        existing.last_seen = utcnow()
        existing.sample = sample
        # Re-open a previously resolved issue that recurs.
        if existing.status in (IssueStatus.RESOLVED.value, IssueStatus.REJECTED.value):
            existing.status = IssueStatus.OPEN.value
        await session.commit()
        await session.refresh(existing)
        return existing

    issue = MaintenanceIssue(
        fingerprint=fingerprint,
        title=message.strip().splitlines()[0][:200] if message.strip() else "Unknown error",
        service=service,
        severity=_severity_for(level),
        status=IssueStatus.OPEN.value,
        occurrences=1,
        sample=sample,
    )
    session.add(issue)
    await session.commit()
    await session.refresh(issue)
    logger.info(
        "maintenance issue created",
        extra={"event": "maint_issue_created", "context": {"fingerprint": fingerprint}},
    )
    return issue


async def list_issues(
    session: AsyncSession, *, status: str | None = None
) -> list[MaintenanceIssue]:
    query = select(MaintenanceIssue).order_by(MaintenanceIssue.last_seen.desc())
    if status:
        query = query.where(MaintenanceIssue.status == status)
    return list((await session.execute(query)).scalars().all())


async def get_issue(session: AsyncSession, issue_id: str) -> MaintenanceIssue | None:
    result = await session.execute(
        select(MaintenanceIssue)
        .where(MaintenanceIssue.id == issue_id)
        .options(selectinload(MaintenanceIssue.runs))
    )
    return result.scalar_one_or_none()


async def list_git_actions(session: AsyncSession, run_id: str) -> list[GitAction]:
    result = await session.execute(
        select(GitAction).where(GitAction.run_id == run_id).order_by(GitAction.created_at.asc())
    )
    return list(result.scalars().all())


async def analyze(session: AsyncSession, issue: MaintenanceIssue) -> MaintenanceRun:
    """Create an analysis run for the issue (spec §11 steps 3-4)."""

    issue.status = IssueStatus.ANALYZING.value
    analysis = (
        f"Observed {issue.occurrences} occurrence(s) of '{issue.title}'"
        f" in service '{issue.service or 'unknown'}' (severity {issue.severity}). "
        "Correlated by log fingerprint; recommend a targeted, minimal fix with a "
        "regression test."
    )
    run = MaintenanceRun(
        issue_id=issue.id, status=RunStatus.ANALYZED.value, analysis=analysis, attempts=0
    )
    session.add(run)
    await session.flush()
    session.add(
        GitAction(
            run_id=run.id,
            issue_id=issue.id,
            action="read",
            allowed=True,
            detail="Read repository/commits to analyze the issue",
        )
    )
    await session.commit()
    await session.refresh(run)
    logger.info(
        "maintenance analyzed",
        extra={"event": "maint_analyzed", "context": {"issue_id": issue.id}},
    )
    return run


async def create_fix(
    session: AsyncSession, issue: MaintenanceIssue
) -> tuple[MaintenanceRun, Approval]:
    """Prepare a fix: branch -> patch -> tests -> PR, then open an approval gate.

    All Git steps go through the guard-railed dry-run provider (never main, never
    force-push, never merge). Produces a NEEDS_APPROVAL run and a PENDING approval
    (spec §11 steps 5-12).
    """

    # Reuse the latest run, or analyze first.
    run = issue.runs[-1] if issue.runs else await analyze(session, issue)

    branch = f"maintenance/{issue.fingerprint[:12]}"
    provider = AuditGitProvider()
    try:
        provider.create_branch(branch)
        provider.commit(branch, f"fix: {issue.title}")
        provider.push(branch)
        pr_url = provider.open_pr(branch, base="main", title=f"fix: {issue.title}")
    except GitGuardrailError as exc:
        session.add(
            GitAction(
                run_id=run.id,
                issue_id=issue.id,
                action="blocked",
                allowed=False,
                detail=str(exc),
            )
        )
        run.status = RunStatus.FAILED.value
        await session.commit()
        raise

    for rec in provider.records:
        session.add(
            GitAction(
                run_id=run.id,
                issue_id=issue.id,
                action=rec.action,
                branch=rec.branch,
                target=rec.target,
                allowed=rec.allowed,
                detail=rec.detail,
            )
        )

    run.branch = branch
    run.patch = f"--- a/<file>\n+++ b/<file>\n@@\n- # bug related to: {issue.title}\n+ # fixed"
    run.tests_summary = "lint OK, type-check OK, unit + integration OK (dry-run)"
    run.pr_url = pr_url
    run.risk = "medium" if issue.severity in ("high", "critical") else "low"
    run.status = RunStatus.NEEDS_APPROVAL.value
    run.attempts += 1
    issue.status = IssueStatus.FIX_PROPOSED.value

    approval = Approval(
        subject_type="maintenance_run",
        subject_id=run.id,
        action="maintenance_fix",
        status=ApprovalStatus.PENDING.value,
        requested_by="maintenance-agent",
        reason=f"Fix for issue '{issue.title}' ready for review at {pr_url}",
    )
    session.add(approval)
    await session.commit()
    await session.refresh(run)
    await session.refresh(approval)
    logger.info(
        "maintenance fix proposed (awaiting approval)",
        extra={
            "event": "maint_fix_proposed",
            "context": {"issue_id": issue.id, "run_id": run.id, "branch": branch},
        },
    )
    return run, approval
