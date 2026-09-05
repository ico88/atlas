"""Runtimes, model deployments & model aliases API (multi-runtime Fase 1).

Local-first: like the existing model/node registries these endpoints are open
(single-operator). RBAC applies when ``ATLAS_AUTH_ENFORCE=true`` at the app level.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.runtime import (
    AliasList,
    AliasUpsert,
    DeploymentCreate,
    DeploymentList,
    DeploymentUpdate,
    ModelAliasRead,
    ModelDeploymentRead,
    RuntimeCreate,
    RuntimeHealthRead,
    RuntimeList,
    RuntimeRead,
    RuntimeUpdate,
)
from app.services import runtime_service

router = APIRouter(prefix="/api/v1", tags=["runtimes"])


# --------------------------------------------------------------------------- #
# Runtimes
# --------------------------------------------------------------------------- #
@router.get("/runtimes", response_model=RuntimeList)
async def list_runtimes(session: AsyncSession = Depends(get_session)) -> RuntimeList:
    items = await runtime_service.list_runtimes(session)
    return RuntimeList(items=[RuntimeRead.model_validate(r) for r in items], total=len(items))


@router.post("/runtimes", response_model=RuntimeRead, status_code=201)
async def create_runtime(
    payload: RuntimeCreate, session: AsyncSession = Depends(get_session)
) -> RuntimeRead:
    if await runtime_service.get_runtime_by_name(session, payload.name):
        raise HTTPException(status_code=409, detail="runtime name already exists")
    runtime = await runtime_service.create_runtime(session, **payload.model_dump())
    return RuntimeRead.model_validate(runtime)


@router.patch("/runtimes/{runtime_id}", response_model=RuntimeRead)
async def update_runtime(
    runtime_id: str, payload: RuntimeUpdate, session: AsyncSession = Depends(get_session)
) -> RuntimeRead:
    runtime = await runtime_service.get_runtime(session, runtime_id)
    if runtime is None:
        raise HTTPException(status_code=404, detail="runtime not found")
    runtime = await runtime_service.update_runtime(
        session, runtime, **payload.model_dump(exclude_unset=True)
    )
    return RuntimeRead.model_validate(runtime)


@router.delete("/runtimes/{runtime_id}")
async def delete_runtime(
    runtime_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    runtime = await runtime_service.get_runtime(session, runtime_id)
    if runtime is None:
        raise HTTPException(status_code=404, detail="runtime not found")
    await runtime_service.delete_runtime(session, runtime)
    return {"status": "deleted"}


@router.get("/runtimes-health", response_model=list[RuntimeHealthRead])
async def runtimes_health(
    session: AsyncSession = Depends(get_session),
) -> list[RuntimeHealthRead]:
    return [RuntimeHealthRead(**h) for h in await runtime_service.health_all(session)]


# --------------------------------------------------------------------------- #
# Deployments
# --------------------------------------------------------------------------- #
@router.get("/model-deployments", response_model=DeploymentList)
async def list_deployments(session: AsyncSession = Depends(get_session)) -> DeploymentList:
    items = await runtime_service.list_deployments(session)
    return DeploymentList(
        items=[ModelDeploymentRead.model_validate(d) for d in items], total=len(items)
    )


@router.post("/model-deployments", response_model=ModelDeploymentRead, status_code=201)
async def create_deployment(
    payload: DeploymentCreate, session: AsyncSession = Depends(get_session)
) -> ModelDeploymentRead:
    if await runtime_service.get_runtime(session, payload.runtime_id) is None:
        raise HTTPException(status_code=400, detail="runtime_id does not exist")
    dep = await runtime_service.create_deployment(session, **payload.model_dump())
    return ModelDeploymentRead.model_validate(dep)


@router.patch("/model-deployments/{dep_id}", response_model=ModelDeploymentRead)
async def update_deployment(
    dep_id: str, payload: DeploymentUpdate, session: AsyncSession = Depends(get_session)
) -> ModelDeploymentRead:
    dep = await runtime_service.get_deployment(session, dep_id)
    if dep is None:
        raise HTTPException(status_code=404, detail="deployment not found")
    dep = await runtime_service.update_deployment(
        session, dep, **payload.model_dump(exclude_unset=True)
    )
    return ModelDeploymentRead.model_validate(dep)


@router.delete("/model-deployments/{dep_id}")
async def delete_deployment(
    dep_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    dep = await runtime_service.get_deployment(session, dep_id)
    if dep is None:
        raise HTTPException(status_code=404, detail="deployment not found")
    await runtime_service.delete_deployment(session, dep)
    return {"status": "deleted"}


# --------------------------------------------------------------------------- #
# Aliases
# --------------------------------------------------------------------------- #
@router.get("/model-aliases", response_model=AliasList)
async def list_aliases(session: AsyncSession = Depends(get_session)) -> AliasList:
    items = await runtime_service.list_aliases(session)
    return AliasList(items=[ModelAliasRead.model_validate(a) for a in items], total=len(items))


@router.put("/model-aliases", response_model=ModelAliasRead)
async def upsert_alias(
    payload: AliasUpsert, session: AsyncSession = Depends(get_session)
) -> ModelAliasRead:
    row = await runtime_service.upsert_alias(
        session,
        alias=payload.alias,
        targets=payload.targets,
        description=payload.description,
        enabled=payload.enabled,
    )
    return ModelAliasRead.model_validate(row)


@router.delete("/model-aliases/{alias}")
async def delete_alias(alias: str, session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    rows = await runtime_service.list_aliases(session)
    match = next((a for a in rows if a.alias == alias), None)
    if match is None:
        raise HTTPException(status_code=404, detail="alias not found")
    await runtime_service.delete_alias(session, match)
    return {"status": "deleted"}
