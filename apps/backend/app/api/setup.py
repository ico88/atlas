"""Guided setup API — make configuration & model distribution easy.

One place the UI can call to answer "what's my hardware, what model should I use,
what's installed, what's active" and to install/activate a model in one step. The
heavy multi-runtime wiring is done for the user by ``autoconfig_service``.
"""

from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.ollama import OllamaProvider
from app.core.hardware import scan_hardware
from app.db import get_session
from app.models.provider import LLMModel
from app.models.runtime import ModelDeployment
from app.services import (
    autoconfig_service,
    recommend_service,
    registry_service,
    settings_service,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/setup", tags=["setup"])

_MODEL_RE = re.compile(r"^[a-zA-Z0-9._:/-]{1,128}$")


class ModelChoice(BaseModel):
    model: str = Field(min_length=1, max_length=128)


@router.get("/status")
async def setup_status(session: AsyncSession = Depends(get_session)) -> dict:
    """Everything the wizard needs in one call."""

    hw = scan_hardware()
    reco = recommend_service.recommend_models(hw)

    settings = await settings_service.get_effective_settings()
    ollama = OllamaProvider(settings.ollama_url) if settings.ollama_url else None
    ollama_ready = bool(ollama and await ollama.is_available())
    installed = (
        [m.name for m in await ollama.list_models()] if ollama_ready and ollama else []
    )

    active_model = settings.default_model or None
    deployments = (
        await session.execute(select(ModelDeployment).where(ModelDeployment.enabled.is_(True)))
    ).scalars().all()
    configured = active_model is not None and any(
        d.model_key == active_model for d in deployments
    )

    return {
        "hardware": {
            "cpu_cores": hw.get("cpu_cores"),
            "ram_total_mb": hw.get("ram_total_mb"),
            "gpu": hw.get("gpu"),
            "recommended_ollama_backend": hw.get("recommended_ollama_backend"),
        },
        "recommendation": reco,
        "ollama_ready": ollama_ready,
        "installed_models": installed,
        "active_model": active_model,
        "configured": configured,
        "deployments": len(deployments),
    }


@router.post("/install", status_code=202)
async def setup_install(payload: ModelChoice) -> dict:
    """Download a model, then auto-configure + activate it on completion.

    Non-blocking: returns immediately; poll ``/api/v1/models/pull-status``.
    """

    if not _MODEL_RE.match(payload.model):
        raise HTTPException(status_code=400, detail="invalid model name")
    # Reuse the models pull worker, which now auto-configures on success.
    from app.api.models import _pull_status, _pull_worker

    _pull_status[payload.model] = {"state": "starting", "status": "queued"}
    asyncio.create_task(_pull_worker(payload.model))  # noqa: RUF006
    return {"status": "started", "model": payload.model}


@router.post("/activate")
async def setup_activate(
    payload: ModelChoice, session: AsyncSession = Depends(get_session)
) -> dict:
    """Activate an already-installed model (wire + set default), no download."""

    if not _MODEL_RE.match(payload.model):
        raise HTTPException(status_code=400, detail="invalid model name")
    # Make sure the registry knows about it (refresh from Ollama if reachable).
    llm = (
        await session.execute(
            select(LLMModel).where(
                LLMModel.provider == "ollama", LLMModel.name == payload.model
            )
        )
    ).scalar_one_or_none()
    if llm is None:
        await registry_service.refresh_models(session)
    return await autoconfig_service.activate_model(session, payload.model)
