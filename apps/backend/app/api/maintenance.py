"""Maintenance Agent API (spec §11, §15)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.maintenance.git import GitGuardrailError
from app.maintenance.sandbox import run_sandbox
from app.schemas.escalation import EscalationRead
from app.schemas.maintenance import (
    IssueDetail,
    IssueList,
    IssueSummary,
    LogIngest,
    RunRead,
    SandboxRequest,
    SandboxResultRead,
)
from app.services import code_review_service, escalation_service, maintenance_service
from app.services.maintenance_service import MaintenanceStateError

router = APIRouter(prefix="/api/v1/maintenance", tags=["maintenance"])


@router.post("/self-review", status_code=200)
async def self_review(
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    """Scan ATLAS's own code now and file findings as issues (awaiting approval).

    Propose-only: nothing edits the repository. Returns how many files were
    scanned, how many findings were seen, and how many were new issues.
    """

    return await code_review_service.run_self_review(session)


@router.post("/logs", response_model=IssueSummary, status_code=201)
async def ingest_log(
    payload: LogIngest,
    session: AsyncSession = Depends(get_session),
) -> IssueSummary:
    """Ingest a structured log event; fingerprints and upserts its issue."""

    issue = await maintenance_service.ingest_log(
        session,
        message=payload.message,
        service=payload.service,
        level=payload.level,
        event=payload.event,
        context=payload.context,
    )
    return IssueSummary.model_validate(issue)


@router.get("/issues", response_model=IssueList)
async def list_issues(
    status_filter: str | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_session),
) -> IssueList:
    issues = await maintenance_service.list_issues(session, status=status_filter)
    return IssueList(
        items=[IssueSummary.model_validate(i) for i in issues], total=len(issues)
    )


@router.get("/issues/{issue_id}", response_model=IssueDetail)
async def get_issue(
    issue_id: str,
    session: AsyncSession = Depends(get_session),
) -> IssueDetail:
    issue = await maintenance_service.get_issue(session, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    detail = IssueDetail.model_validate(issue)
    detail.runs = [RunRead.model_validate(r) for r in issue.runs]
    return detail


@router.post("/issues/{issue_id}/dismiss", response_model=IssueSummary)
async def dismiss_issue(
    issue_id: str,
    session: AsyncSession = Depends(get_session),
) -> IssueSummary:
    """Ignore an issue (e.g. a self-review finding you won't act on)."""

    issue = await maintenance_service.get_issue(session, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    return IssueSummary.model_validate(await maintenance_service.dismiss_issue(session, issue))


@router.post("/issues/{issue_id}/analyze", response_model=RunRead)
async def analyze_issue(
    issue_id: str,
    session: AsyncSession = Depends(get_session),
) -> RunRead:
    issue = await maintenance_service.get_issue(session, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    run = await maintenance_service.analyze(session, issue)
    return RunRead.model_validate(run)


@router.post("/issues/{issue_id}/create-fix", response_model=RunRead)
async def create_fix(
    issue_id: str,
    session: AsyncSession = Depends(get_session),
) -> RunRead:
    issue = await maintenance_service.get_issue(session, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    try:
        run, _approval = await maintenance_service.create_fix(session, issue)
    except GitGuardrailError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RunRead.model_validate(run)


@router.post("/issues/{issue_id}/apply-fix", response_model=RunRead)
async def apply_fix(
    issue_id: str,
    session: AsyncSession = Depends(get_session),
) -> RunRead:
    """Open the real PR for an APPROVED fix (governed; guardrails enforced)."""

    issue = await maintenance_service.get_issue(session, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    try:
        run = await maintenance_service.apply_fix(session, issue)
    except MaintenanceStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except GitGuardrailError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RunRead.model_validate(run)


@router.post("/sandbox", response_model=SandboxResultRead)
async def sandbox(payload: SandboxRequest) -> SandboxResultRead:
    """Apply a patch to seed files in the real, isolated sandbox and report results.

    The validation command is taken from server config only (never the request),
    so this cannot execute arbitrary commands.
    """

    from app.core.config import get_settings

    settings = get_settings()
    result = run_sandbox(
        payload.files,
        payload.patch,
        check_command=settings.maintenance_check_command or None,
        timeout=settings.maintenance_sandbox_timeout,
    )
    return SandboxResultRead(**result.to_dict())


@router.post("/issues/{issue_id}/prepare-external", response_model=EscalationRead)
async def prepare_external(
    issue_id: str,
    target: str = Query(default="chatgpt"),
    session: AsyncSession = Depends(get_session),
) -> EscalationRead:
    """Build a ChatGPT/Claude escalation package from an issue (spec §10, §15)."""

    issue = await maintenance_service.get_issue(session, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    escalation = await escalation_service.prepare_for_issue(session, issue, target=target)
    return EscalationRead.model_validate(escalation)
