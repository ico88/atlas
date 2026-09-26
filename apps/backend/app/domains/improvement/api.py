"""Improvement & Quality domain API — Autopilot, Fine-tuning, Code Review, Evals.

Improvement domain: Autonomous model improvements, fine-tuning experiments,
code review, evaluation metrics, and self-improvement workflows.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.improvement import (
    AutopilotRead,
    EvalCreate,
    EvalList,
    EvalRead,
    EvalRunCreate,
    EvalRunList,
    EvalRunRead,
    ImprovementList,
    ImprovementRead,
    ImprovementUpdate,
    CodeReviewRead,
    CodeReviewList,
)
from app.domains.improvement import autopilot, service, finetune, code_review, eval as eval_module
from app.services import benchmark_service

router = APIRouter(tags=["improvement"])

# ============================================================================
# Autopilot
# ============================================================================

autopilot_router = APIRouter(prefix="/api/v1/autopilot", tags=["autopilot"])


@autopilot_router.get("", response_model=AutopilotRead)
async def get_autopilot_status(session: AsyncSession = Depends(get_session)) -> AutopilotRead:
    return AutopilotRead(enabled=True, experiments_running=0, success_rate=0.92)


@autopilot_router.post("/start")
async def start_autopilot(session: AsyncSession = Depends(get_session)):
    return {"status": "autopilot started"}


@autopilot_router.post("/stop")
async def stop_autopilot(session: AsyncSession = Depends(get_session)):
    return {"status": "autopilot stopped"}


# ============================================================================
# Improvements
# ============================================================================

improvements_router = APIRouter(prefix="/api/v1/improvements", tags=["improvements"])


@improvements_router.get("", response_model=ImprovementList)
async def list_improvements(
    status: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> ImprovementList:
    items = await service.list_improvements(session)
    if status:
        items = [i for i in items if i.status == status]
    return ImprovementList(
        items=[ImprovementRead.model_validate(i) for i in items], total=len(items)
    )


@improvements_router.patch("/{improvement_id}", response_model=ImprovementRead)
async def update_improvement(
    improvement_id: str,
    payload: ImprovementUpdate,
    session: AsyncSession = Depends(get_session),
) -> ImprovementRead:
    imp = await service.get_improvement(session, improvement_id)
    if imp is None:
        raise HTTPException(status_code=404, detail="improvement not found")
    imp = await service.update_improvement(session, imp, **payload.model_dump(exclude_unset=True))
    return ImprovementRead.model_validate(imp)


# ============================================================================
# Code Review
# ============================================================================

review_router = APIRouter(prefix="/api/v1/reviews", tags=["reviews"])


@review_router.get("", response_model=CodeReviewList)
async def list_reviews(session: AsyncSession = Depends(get_session)) -> CodeReviewList:
    items = await code_review.list_reviews(session)
    return CodeReviewList(
        items=[CodeReviewRead.model_validate(r) for r in items], total=len(items)
    )


@review_router.get("/{review_id}", response_model=CodeReviewRead)
async def get_review(
    review_id: str, session: AsyncSession = Depends(get_session)
) -> CodeReviewRead:
    review = await code_review.get_review(session, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    return CodeReviewRead.model_validate(review)


@review_router.post("/{review_id}/approve")
async def approve_review(
    review_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    review = await code_review.get_review(session, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    return {"status": "approved"}


@review_router.post("/{review_id}/reject")
async def reject_review(review_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    review = await code_review.get_review(session, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    return {"status": "rejected"}


# ============================================================================
# Evals
# ============================================================================

evals_router = APIRouter(prefix="/api/v1/evals", tags=["evals"])


@evals_router.get("", response_model=EvalList)
async def list_evals(session: AsyncSession = Depends(get_session)) -> EvalList:
    items = await eval_module.list_evals(session)
    return EvalList(items=[EvalRead.model_validate(e) for e in items], total=len(items))


@evals_router.post("", response_model=EvalRead, status_code=201)
async def create_eval(
    payload: EvalCreate, session: AsyncSession = Depends(get_session)
) -> EvalRead:
    ev = await eval_module.create_eval(session, **payload.model_dump())
    return EvalRead.model_validate(ev)


@evals_router.get("/{eval_id}", response_model=EvalRead)
async def get_eval(eval_id: str, session: AsyncSession = Depends(get_session)) -> EvalRead:
    ev = await eval_module.get_eval(session, eval_id)
    if ev is None:
        raise HTTPException(status_code=404, detail="eval not found")
    return EvalRead.model_validate(ev)


@evals_router.get("/{eval_id}/runs", response_model=EvalRunList)
async def list_eval_runs(eval_id: str, session: AsyncSession = Depends(get_session)):
    runs = await eval_module.list_runs(session, eval_id)
    return EvalRunList(items=[EvalRunRead.model_validate(r) for r in runs], total=len(runs))


@evals_router.post("/{eval_id}/runs", response_model=EvalRunRead, status_code=201)
async def run_eval(
    eval_id: str, payload: EvalRunCreate, session: AsyncSession = Depends(get_session)
):
    ev = await eval_module.get_eval(session, eval_id)
    if ev is None:
        raise HTTPException(status_code=404, detail="eval not found")
    run = await eval_module.create_run(session, eval_id, **payload.model_dump())
    return EvalRunRead.model_validate(run)


# ============================================================================
# Fine-tuning
# ============================================================================

finetune_router = APIRouter(prefix="/api/v1/finetune", tags=["finetune"])


@finetune_router.get("")
async def list_finetune_jobs(session: AsyncSession = Depends(get_session)):
    return {"jobs": []}


@finetune_router.post("")
async def create_finetune_job(
    payload: dict, session: AsyncSession = Depends(get_session)
) -> dict:
    return {"job_id": "ft-123", "status": "queued"}


@finetune_router.get("/{job_id}")
async def get_finetune_job(job_id: str, session: AsyncSession = Depends(get_session)):
    return {"job_id": job_id, "status": "running"}


# ============================================================================
# Aggregate all improvement routers
# ============================================================================

router.include_router(autopilot_router)
router.include_router(improvements_router)
router.include_router(review_router)
router.include_router(evals_router)
router.include_router(finetune_router)
