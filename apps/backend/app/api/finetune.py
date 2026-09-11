"""Local fine-tuning API (ROADMAP self-improvement).

Curate a dataset from good interactions, train a LoRA adapter on a GPU node, and
adopt the result through the standard eval + canary guardrails.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.finetune import (
    CurateRequest,
    CurateResult,
    DatasetCreate,
    DatasetList,
    DatasetRead,
    ExampleCreate,
    ExampleIncluded,
    ExampleList,
    ExampleRead,
    JobCreate,
    JobList,
    JobRead,
    Readiness,
)
from app.schemas.improvement import ProposalRead
from app.services import finetune_service
from app.services.finetune_service import FineTuneError

router = APIRouter(prefix="/api/v1/finetune", tags=["finetune"])


@router.get("/readiness", response_model=Readiness)
async def readiness(session: AsyncSession = Depends(get_session)) -> Readiness:
    return Readiness(**await finetune_service.readiness(session))


# --- datasets ---------------------------------------------------------------


@router.post("/datasets", response_model=DatasetRead, status_code=201)
async def create_dataset(
    payload: DatasetCreate, session: AsyncSession = Depends(get_session)
) -> DatasetRead:
    ds = await finetune_service.create_dataset(
        session,
        name=payload.name,
        description=payload.description,
        base_model=payload.base_model,
    )
    return DatasetRead.model_validate(ds)


@router.get("/datasets", response_model=DatasetList)
async def list_datasets(session: AsyncSession = Depends(get_session)) -> DatasetList:
    items = await finetune_service.list_datasets(session)
    return DatasetList(
        items=[DatasetRead.model_validate(d) for d in items], total=len(items)
    )


async def _require_dataset(session: AsyncSession, dataset_id: str):
    ds = await finetune_service.get_dataset(session, dataset_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return ds


@router.delete("/datasets/{dataset_id}", status_code=200)
async def delete_dataset(
    dataset_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    ds = await _require_dataset(session, dataset_id)
    await finetune_service.delete_dataset(session, ds)
    return {"status": "deleted"}


@router.get("/datasets/{dataset_id}/examples", response_model=ExampleList)
async def list_examples(
    dataset_id: str, session: AsyncSession = Depends(get_session)
) -> ExampleList:
    await _require_dataset(session, dataset_id)
    items = await finetune_service.list_examples(session, dataset_id)
    return ExampleList(
        items=[ExampleRead.model_validate(e) for e in items], total=len(items)
    )


@router.post("/datasets/{dataset_id}/examples", response_model=ExampleRead, status_code=201)
async def add_example(
    dataset_id: str,
    payload: ExampleCreate,
    session: AsyncSession = Depends(get_session),
) -> ExampleRead:
    await _require_dataset(session, dataset_id)
    ex = await finetune_service.add_example(
        session,
        dataset_id=dataset_id,
        prompt=payload.prompt,
        response=payload.response,
        system_prompt=payload.system_prompt,
        quality=payload.quality,
    )
    if ex is None:
        raise HTTPException(status_code=409, detail="Duplicate example")
    return ExampleRead.model_validate(ex)


@router.patch("/examples/{example_id}", response_model=ExampleRead)
async def set_example_included(
    example_id: str,
    payload: ExampleIncluded,
    session: AsyncSession = Depends(get_session),
) -> ExampleRead:
    ex = await session.get(finetune_service.FineTuneExample, example_id)
    if ex is None:
        raise HTTPException(status_code=404, detail="Example not found")
    ex = await finetune_service.set_example_included(session, ex, payload.included)
    return ExampleRead.model_validate(ex)


@router.post("/datasets/{dataset_id}/curate", response_model=CurateResult)
async def curate(
    dataset_id: str,
    payload: CurateRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> CurateResult:
    await _require_dataset(session, dataset_id)
    min_rating = payload.min_rating if payload else 1
    added = await finetune_service.curate_from_feedback(
        session, dataset_id=dataset_id, min_rating=min_rating
    )
    return CurateResult(added=added)


@router.get("/datasets/{dataset_id}/export", response_class=PlainTextResponse)
async def export_dataset(
    dataset_id: str, session: AsyncSession = Depends(get_session)
) -> str:
    await _require_dataset(session, dataset_id)
    examples = await finetune_service.list_examples(session, dataset_id)
    return finetune_service.build_jsonl(examples)


# --- jobs -------------------------------------------------------------------


@router.post("/jobs", response_model=JobRead, status_code=201)
async def create_job(
    payload: JobCreate, session: AsyncSession = Depends(get_session)
) -> JobRead:
    try:
        job = await finetune_service.create_job(
            session,
            dataset_id=payload.dataset_id,
            base_model=payload.base_model,
            adapter_name=payload.adapter_name,
            hyperparams=payload.hyperparams,
        )
    except FineTuneError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JobRead.model_validate(job)


@router.get("/jobs", response_model=JobList)
async def list_jobs(
    dataset_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> JobList:
    items = await finetune_service.list_jobs(session, dataset_id=dataset_id)
    # Reflect the latest dispatched-task state before returning.
    items = [await finetune_service.sync_job(session, j) for j in items]
    return JobList(items=[JobRead.model_validate(j) for j in items], total=len(items))


async def _require_job(session: AsyncSession, job_id: str):
    job = await finetune_service.get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs/{job_id}", response_model=JobRead)
async def get_job(job_id: str, session: AsyncSession = Depends(get_session)) -> JobRead:
    job = await _require_job(session, job_id)
    job = await finetune_service.sync_job(session, job)
    return JobRead.model_validate(job)


@router.post("/jobs/{job_id}/adopt", response_model=ProposalRead, status_code=201)
async def adopt_job(job_id: str, session: AsyncSession = Depends(get_session)) -> ProposalRead:
    job = await _require_job(session, job_id)
    job = await finetune_service.sync_job(session, job)
    try:
        proposal = await finetune_service.adopt_job(session, job)
    except FineTuneError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProposalRead.model_validate(proposal)
