"""Environment API (ROADMAP PR 13): CRUD, manifest, snapshot/restore."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.environment import (
    EnvironmentCreate,
    EnvironmentList,
    EnvironmentRead,
    EnvironmentUpdate,
    SnapshotCreate,
    SnapshotList,
    SnapshotRead,
)
from app.services import environment_service

router = APIRouter(prefix="/api/v1/environments", tags=["environments"])


@router.post("", response_model=EnvironmentRead, status_code=201)
async def create_environment(
    payload: EnvironmentCreate,
    session: AsyncSession = Depends(get_session),
) -> EnvironmentRead:
    env = await environment_service.create_environment(
        session,
        name=payload.name,
        description=payload.description,
        manifest=payload.manifest,
        variables=payload.variables,
    )
    return EnvironmentRead.model_validate(env)


@router.get("", response_model=EnvironmentList)
async def list_environments(
    include_archived: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
) -> EnvironmentList:
    items = await environment_service.list_environments(
        session, include_archived=include_archived
    )
    return EnvironmentList(
        items=[EnvironmentRead.model_validate(e) for e in items], total=len(items)
    )


async def _load(session: AsyncSession, ref: str):
    env = await environment_service.get_by_ref(session, ref)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found")
    return env


@router.get("/{ref}", response_model=EnvironmentRead)
async def get_environment(
    ref: str, session: AsyncSession = Depends(get_session)
) -> EnvironmentRead:
    return EnvironmentRead.model_validate(await _load(session, ref))


@router.patch("/{ref}", response_model=EnvironmentRead)
async def update_environment(
    ref: str,
    payload: EnvironmentUpdate,
    session: AsyncSession = Depends(get_session),
) -> EnvironmentRead:
    env = await _load(session, ref)
    env = await environment_service.update_environment(
        session,
        env,
        name=payload.name,
        description=payload.description,
        manifest=payload.manifest,
        variables=payload.variables,
        status=payload.status,
    )
    return EnvironmentRead.model_validate(env)


@router.post("/{ref}/snapshots", response_model=SnapshotRead, status_code=201)
async def create_snapshot(
    ref: str,
    payload: SnapshotCreate | None = None,
    session: AsyncSession = Depends(get_session),
) -> SnapshotRead:
    env = await _load(session, ref)
    snap = await environment_service.create_snapshot(
        session,
        env,
        name=payload.name if payload else None,
        created_by=payload.created_by if payload else None,
    )
    return SnapshotRead.model_validate(snap)


@router.get("/{ref}/snapshots", response_model=SnapshotList)
async def list_snapshots(
    ref: str, session: AsyncSession = Depends(get_session)
) -> SnapshotList:
    env = await _load(session, ref)
    items = await environment_service.list_snapshots(session, env.id)
    return SnapshotList(
        items=[SnapshotRead.model_validate(s) for s in items], total=len(items)
    )


@router.post("/snapshots/{snapshot_id}/restore", response_model=EnvironmentRead)
async def restore_snapshot(
    snapshot_id: str, session: AsyncSession = Depends(get_session)
) -> EnvironmentRead:
    snapshot = await environment_service.get_snapshot(session, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    try:
        env = await environment_service.restore_snapshot(session, snapshot)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return EnvironmentRead.model_validate(env)
