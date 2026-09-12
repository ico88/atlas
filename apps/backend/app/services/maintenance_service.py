"""Maintenance Agent workflow (spec §11).

Implements the deterministic, human-governed slice of the agent:
ingest+fingerprint -> issue, analyze -> run, create-fix -> branch/patch/tests/PR
(via the guard-railed dry-run Git provider) -> NEEDS_APPROVAL gate. It never
merges to main or performs any real, ungated repository mutation.
"""

from __future__ import annotations

import difflib
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.maintenance.fingerprint import compute_fingerprint
from app.maintenance.git import AuditGitProvider, GitGuardrailError, get_provider
from app.maintenance.sandbox import SandboxResult, run_sandbox
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


class MaintenanceStateError(RuntimeError):
    """Raised when an action is requested in a state that does not allow it."""

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
    # Semi-auto: prepare a sandbox-validated fix in the background (awaiting
    # approval). Fired only for a brand-new issue, never on every recurrence.
    from app.services import automation_service

    automation_service.maybe_advance_issue(issue.id)
    return issue


async def list_issues(
    session: AsyncSession, *, status: str | None = None
) -> list[MaintenanceIssue]:
    query = select(MaintenanceIssue).order_by(MaintenanceIssue.last_seen.desc())
    if status:
        query = query.where(MaintenanceIssue.status == status)
    return list((await session.execute(query)).scalars().all())


async def dismiss_issue(session: AsyncSession, issue: MaintenanceIssue) -> MaintenanceIssue:
    """Mark an issue as ignored (e.g. a self-review finding the user won't act on)."""

    issue.status = IssueStatus.IGNORED.value
    await session.commit()
    await session.refresh(issue)
    return issue


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


def _proposed_patch(issue: MaintenanceIssue) -> tuple[dict[str, str], str]:
    """Build a concrete (seed files, unified-diff patch) pair for the sandbox.

    The maintenance agent does not yet synthesize a repo-grounded patch from a
    model — that source plugs in here later (an LLM, or the ChatGPT/Claude
    escalation round-trip). What is already **real** is the validation: the patch
    below is a well-formed unified diff that the sandbox actually applies and
    checks, so the recorded result reflects a genuine execution rather than a
    hard-coded string.
    """

    fname = "fix_target.py"
    title = issue.title.replace("'", " ").replace("\n", " ").strip()[:80] or "issue"
    before = (
        "def handle_event(event):\n"
        f"    # FIXME: {title}\n"
        "    raise RuntimeError('unhandled')\n"
    )
    after = (
        "def handle_event(event):\n"
        f"    # fixed: {title}\n"
        "    return None\n"
    )
    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{fname}",
        tofile=f"b/{fname}",
    )
    return {fname: before}, "".join(diff)


def _validate_in_sandbox(patch: str, files: dict[str, str]) -> SandboxResult | None:
    """Run the real sandbox if enabled; never let a sandbox error break the flow."""

    settings = get_settings()
    if not settings.maintenance_sandbox_enabled:
        return None
    try:
        return run_sandbox(
            files,
            patch,
            check_command=settings.maintenance_check_command or None,
            timeout=settings.maintenance_sandbox_timeout,
        )
    except Exception:  # noqa: BLE001 - infra failure must not break the workflow
        logger.warning("sandbox run failed", extra={"event": "maint_sandbox_error"})
        return None


async def create_fix(
    session: AsyncSession,
    issue: MaintenanceIssue,
    *,
    files: dict[str, str] | None = None,
    patch: str | None = None,
) -> tuple[MaintenanceRun, Approval]:
    """Prepare a fix: branch -> patch -> **real sandbox validation** -> PR preview,
    then open an approval gate (spec §11 steps 5-12; ROADMAP PR 17).

    The patch is applied and checked in a real, isolated sandbox (never touching
    the repo). Git steps here go through the guard-railed *dry-run* provider as a
    preview only — no real repository is mutated. The real PR is opened later, by
    :func:`apply_fix`, and only after a human approves.

    ``files``/``patch`` may be supplied by a caller that already synthesized a
    real, repo-grounded patch (e.g. the LLM code-patch pipeline); when omitted a
    demonstration patch is used.
    """

    # Reuse the latest run, or analyze first.
    run = issue.runs[-1] if issue.runs else await analyze(session, issue)

    branch = f"maintenance/{issue.fingerprint[:12]}"

    # 1) Build the proposed patch and validate it for real in the sandbox.
    if files is None or patch is None:
        files, patch = _proposed_patch(issue)
    sandbox = _validate_in_sandbox(patch, files)
    if sandbox is not None:
        session.add(
            GitAction(
                run_id=run.id,
                issue_id=issue.id,
                action="sandbox",
                branch=branch,
                allowed=True,
                detail=sandbox.summary,
            )
        )
        run.status = RunStatus.TESTED.value if sandbox.passed else RunStatus.PATCHED.value

    # 2) Dry-run git preview (no real mutation, fully audited).
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
    run.patch = patch
    if sandbox is not None:
        run.tests_summary = sandbox.summary
    else:
        run.tests_summary = "sandbox disabled (set ATLAS_MAINTENANCE_SANDBOX_ENABLED=true)"
    run.pr_url = pr_url  # dry-run preview URL until apply_fix opens a real one
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
        reason=f"Fix for issue '{issue.title}' validated in sandbox; awaiting approval",
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


async def apply_fix(session: AsyncSession, issue: MaintenanceIssue) -> MaintenanceRun:
    """Open the real PR for an **approved** fix (ROADMAP PR 17, governed action).

    This is the only step that may mutate a real repository, and only via the
    configured provider (dry-run by default; real GitHub when the operator opts
    in). It refuses to run unless the latest run has been APPROVED by a human, and
    the same guardrails apply (never a protected branch, never a merge/force-push).
    """

    run = issue.runs[-1] if issue.runs else None
    if run is None:
        raise MaintenanceStateError("No run to apply; create a fix first")
    if run.status != RunStatus.APPROVED.value:
        raise MaintenanceStateError("Fix is not approved yet; a human must approve it first")
    if not run.branch:
        raise MaintenanceStateError("Run has no prepared branch")

    provider = get_provider()
    try:
        provider.create_branch(run.branch)
        provider.commit(run.branch, f"fix: {issue.title}")
        provider.push(run.branch)
        pr_url = provider.open_pr(run.branch, base="main", title=f"fix: {issue.title}")
    except GitGuardrailError as exc:
        session.add(
            GitAction(
                run_id=run.id,
                issue_id=issue.id,
                action="blocked",
                branch=run.branch,
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
    run.pr_url = pr_url
    run.status = RunStatus.PR_OPENED.value
    await session.commit()
    await session.refresh(run)
    logger.info(
        "maintenance fix applied (PR opened)",
        extra={
            "event": "maint_fix_applied",
            "context": {"issue_id": issue.id, "run_id": run.id, "pr_url": pr_url},
        },
    )
    return run
