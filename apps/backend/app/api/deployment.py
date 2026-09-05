"""Fleet deployment API (ROADMAP PR 21 / PR 22)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.deployment import (
    DeploymentCreate,
    DeploymentList,
    DeploymentRead,
    DeploymentSummary,
    ReportRequest,
)
from app.services import deployment_service
from app.services.deployment_service import DeploymentStateError

router = APIRouter(prefix="/api/v1/deployments", tags=["deployments"])


@router.post("", response_model=DeploymentRead, status_code=201)
async def create_deployment(
    payload: DeploymentCreate,
    session: AsyncSession = Depends(get_session),
) -> DeploymentRead:
    dep = await deployment_service.create_deployment(
        session,
        target_version=payload.target_version,
        canary_count=payload.canary_count,
        min_compatible=payload.min_compatible,
        note=payload.note,
    )
    return DeploymentRead.model_validate(dep)


@router.get("", response_model=DeploymentList)
async def list_deployments(session: AsyncSession = Depends(get_session)) -> DeploymentList:
    items = await deployment_service.list_deployments(session)
    return DeploymentList(
        items=[DeploymentSummary.model_validate(d) for d in items], total=len(items)
    )


@router.get("/{deployment_id}", response_model=DeploymentRead)
async def get_deployment(
    deployment_id: str,
    session: AsyncSession = Depends(get_session),
) -> DeploymentRead:
    dep = await deployment_service.get_deployment(session, deployment_id)
    if dep is None:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return DeploymentRead.model_validate(dep)


@router.post("/{deployment_id}/report", response_model=DeploymentRead)
async def report_result(
    deployment_id: str,
    payload: ReportRequest,
    session: AsyncSession = Depends(get_session),
) -> DeploymentRead:
    try:
        await deployment_service.report_result(
            session,
            deployment_id,
            payload.node_ref,
            version=payload.version,
            healthy=payload.healthy,
        )
    except DeploymentStateError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    dep = await deployment_service.get_deployment(session, deployment_id)
    return DeploymentRead.model_validate(dep)


@router.post("/{deployment_id}/advance", response_model=DeploymentRead)
async def advance(
    deployment_id: str,
    session: AsyncSession = Depends(get_session),
) -> DeploymentRead:
    try:
        dep = await deployment_service.advance(session, deployment_id)
    except DeploymentStateError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DeploymentRead.model_validate(dep)
