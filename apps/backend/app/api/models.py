"""Model registry API (spec §14, M2) + UI model management (pull/default/delete)."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.ollama import OllamaProvider
from app.db import get_session, get_sessionmaker
from app.schemas.registry import ModelList, ModelRead
from app.services import registry_service, settings_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/models", tags=["models"])

# In-memory pull progress, keyed by model name (best-effort UI feedback).
_pull_status: dict[str, dict[str, Any]] = {}
_MODEL_RE = re.compile(r"^[a-zA-Z0-9._:/-]{1,128}$")


class ModelName(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class DefaultModel(BaseModel):
    model: str = Field(default="", max_length=128)


@router.get("", response_model=ModelList)
async def list_models(session: AsyncSession = Depends(get_session)) -> ModelList:
    models = await registry_service.list_models(session)
    return ModelList(items=[ModelRead.model_validate(m) for m in models], total=len(models))


@router.post("/refresh", response_model=ModelList)
async def refresh_models(session: AsyncSession = Depends(get_session)) -> ModelList:
    models = await registry_service.refresh_models(session)
    return ModelList(items=[ModelRead.model_validate(m) for m in models], total=len(models))


@router.get("/default")
async def get_default() -> dict[str, str]:
    return await settings_service.get_ai_config_public()


@router.post("/default")
async def set_default(payload: DefaultModel) -> dict[str, str]:
    return await settings_service.set_ai_config({"default_model": payload.model})


async def _pull_worker(name: str) -> None:
    settings = await settings_service.get_effective_settings()
    provider = OllamaProvider(settings.ollama_url)

    def _progress(chunk: dict[str, Any]) -> None:
        _pull_status[name] = {
            "state": "pulling",
            "status": chunk.get("status", ""),
            "completed": chunk.get("completed"),
            "total": chunk.get("total"),
        }

    ok = await provider.pull_model(name, on_progress=_progress)
    _pull_status[name] = {"state": "done" if ok else "error", "status": "" if ok else "pull failed"}
    if ok:
        async with get_sessionmaker()() as session:
            await registry_service.refresh_models(session)


@router.post("/pull", status_code=202)
async def pull_model(payload: ModelName) -> dict[str, str]:
    if not _MODEL_RE.match(payload.name):
        raise HTTPException(status_code=400, detail="invalid model name")
    _pull_status[payload.name] = {"state": "starting", "status": "queued"}
    asyncio.create_task(_pull_worker(payload.name))  # noqa: RUF006
    return {"status": "started", "model": payload.name}


@router.get("/pull-status")
async def pull_status() -> dict[str, Any]:
    return {"items": _pull_status}


@router.delete("/{name:path}", response_model=ModelList)
async def delete_model(
    name: str, session: AsyncSession = Depends(get_session)
) -> ModelList:
    settings = await settings_service.get_effective_settings()
    provider = OllamaProvider(settings.ollama_url)
    await provider.delete_model(name)
    _pull_status.pop(name, None)
    models = await registry_service.refresh_models(session)
    return ModelList(items=[ModelRead.model_validate(m) for m in models], total=len(models))
