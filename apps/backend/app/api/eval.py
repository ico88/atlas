"""Evaluation API (ROADMAP PR 16): suites, cases, runs, metrics."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.eval import (
    CaseCreate,
    CaseRead,
    ResultRead,
    RunDetail,
    RunList,
    RunRead,
    RunRequest,
    SuiteCreate,
    SuiteDetail,
    SuiteList,
    SuiteRead,
)
from app.services import eval_service

router = APIRouter(prefix="/api/v1/evals", tags=["evals"])


@router.post("/suites", response_model=SuiteRead, status_code=201)
async def create_suite(
    payload: SuiteCreate, session: AsyncSession = Depends(get_session)
) -> SuiteRead:
    suite = await eval_service.create_suite(
        session, name=payload.name, description=payload.description
    )
    return SuiteRead.model_validate(suite)


@router.get("/suites", response_model=SuiteList)
async def list_suites(session: AsyncSession = Depends(get_session)) -> SuiteList:
    items = await eval_service.list_suites(session)
    return SuiteList(items=[SuiteRead.model_validate(s) for s in items], total=len(items))


@router.get("/suites/{suite_id}", response_model=SuiteDetail)
async def get_suite(
    suite_id: str, session: AsyncSession = Depends(get_session)
) -> SuiteDetail:
    suite = await eval_service.get_suite(session, suite_id)
    if suite is None:
        raise HTTPException(status_code=404, detail="Suite not found")
    detail = SuiteDetail.model_validate(suite)
    detail.cases = [CaseRead.model_validate(c) for c in suite.cases]
    return detail


@router.post("/suites/{suite_id}/cases", response_model=CaseRead, status_code=201)
async def add_case(
    suite_id: str, payload: CaseCreate, session: AsyncSession = Depends(get_session)
) -> CaseRead:
    suite = await eval_service.get_suite(session, suite_id)
    if suite is None:
        raise HTTPException(status_code=404, detail="Suite not found")
    case = await eval_service.add_case(
        session,
        suite_id=suite_id,
        input=payload.input,
        expected_substrings=payload.expected_substrings,
        forbidden_substrings=payload.forbidden_substrings,
        category=payload.category,
    )
    return CaseRead.model_validate(case)


@router.post("/suites/{suite_id}/run", response_model=RunRead, status_code=201)
async def run_suite(
    suite_id: str,
    payload: RunRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> RunRead:
    try:
        run = await eval_service.run_suite(
            session,
            suite_id,
            model=payload.model if payload else None,
            is_baseline=payload.is_baseline if payload else False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RunRead.model_validate(run)


@router.get("/suites/{suite_id}/runs", response_model=RunList)
async def list_runs(
    suite_id: str, session: AsyncSession = Depends(get_session)
) -> RunList:
    items = await eval_service.list_runs(session, suite_id)
    return RunList(items=[RunRead.model_validate(r) for r in items], total=len(items))


@router.get("/runs/{run_id}", response_model=RunDetail)
async def get_run(run_id: str, session: AsyncSession = Depends(get_session)) -> RunDetail:
    run = await eval_service.get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    detail = RunDetail.model_validate(run)
    detail.results = [ResultRead.model_validate(r) for r in run.results]
    return detail
