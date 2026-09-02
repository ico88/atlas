"""Model registry API (spec §14, M2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.registry import ModelList, ModelRead
from app.services import registry_service

router = APIRouter(prefix="/api/v1/models", tags=["models"])


@router.get("", response_model=ModelList)
async def list_models(session: AsyncSession = Depends(get_session)) -> ModelList:
    models = await registry_service.list_models(session)
    return ModelList(items=[ModelRead.model_validate(m) for m in models], total=len(models))


@router.post("/refresh", response_model=ModelList)
async def refresh_models(session: AsyncSession = Depends(get_session)) -> ModelList:
    models = await registry_service.refresh_models(session)
    return ModelList(items=[ModelRead.model_validate(m) for m in models], total=len(models))
