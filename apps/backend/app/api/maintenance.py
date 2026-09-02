"""Maintenance Agent API (spec §11, §15)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.maintenance.git import GitGuardrailError
from app.schemas.maintenance import (
    IssueDetail,
    IssueList,
    IssueSummary,
    LogIngest,
    RunRead,
)
from app.services import maintenance_service

router = APIRouter(prefix="/api/v1/maintenance", tags=["maintenance"])


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
