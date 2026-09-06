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
from app.core.config import get_settings
from app.core.hardware import scan_hardware
from app.db import get_session
from app.models.base import utcnow
from app.models.node import Node
from app.models.provider import LLMModel
from app.models.runtime import ModelDeployment, Runtime
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


class NodeAttach(BaseModel):
    node_id: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=128)
    endpoint: str = Field(min_length=1, max_length=255)


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


@router.get("/nodes")
async def setup_nodes(session: AsyncSession = Depends(get_session)) -> dict:
    """Guided per-node setup: each node's hardware + recommended model + whether
    it already has a model attached. Keeps node configuration to one decision."""

    offline_after = get_settings().node_offline_after_seconds
    nodes = (await session.execute(select(Node))).scalars().all()
    runtimes = {
        r.node_id: r
        for r in (await session.execute(select(Runtime))).scalars().all()
        if r.node_id
    }
    deps = (await session.execute(select(ModelDeployment))).scalars().all()
    deps_by_node: dict[str, list[str]] = {}
    for d in deps:
        if d.node_id:
            deps_by_node.setdefault(d.node_id, []).append(d.model_key)

    items = []
    for n in nodes:
        hw = n.hardware or {}
        online = bool(
            n.last_heartbeat
            and (utcnow() - n.last_heartbeat).total_seconds() < offline_after
        )
        reco = recommend_service.recommend_models(hw) if hw else None
        # The node may advertise where its Ollama is reachable (register hardware
        # or heartbeat health) — use it to pre-fill the endpoint in the UI.
        advertised = hw.get("ollama_url") or (hw.get("health") or {}).get("ollama_url")
        items.append(
            {
                "node_id": n.node_id,
                "label": n.label,
                "online": online,
                "hardware": {
                    "cpu_cores": hw.get("cpu_cores"),
                    "ram_total_mb": hw.get("ram_total_mb"),
                    "gpu": hw.get("gpu"),
                },
                "recommendation": reco,
                "ollama_url": advertised,
                "attached_runtime": runtimes[n.node_id].name if n.node_id in runtimes else None,
                "attached_models": deps_by_node.get(n.node_id, []),
            }
        )
    return {"nodes": items, "total": len(items)}


@router.post("/nodes/attach")
async def setup_node_attach(
    payload: NodeAttach, session: AsyncSession = Depends(get_session)
) -> dict:
    """Attach a model to a node in one step (creates runtime + deployment)."""

    if not _MODEL_RE.match(payload.model):
        raise HTTPException(status_code=400, detail="invalid model name")
    node = (
        await session.execute(select(Node).where(Node.node_id == payload.node_id))
    ).scalar_one_or_none()
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")
    return await autoconfig_service.attach_node(
        session, node_id=payload.node_id, model_name=payload.model, endpoint=payload.endpoint
    )


class NodePull(BaseModel):
    node_id: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=128)


@router.post("/nodes/pull", status_code=202)
async def setup_node_pull(
    payload: NodePull, session: AsyncSession = Depends(get_session)
) -> dict:
    """Tell a node to download a model into its local Ollama (one-click).

    Creates a ``model_pull`` task pinned to the node; the node agent claims it and
    pulls via its local Ollama, then reports back. Poll /api/v1/tasks/{id}.
    """

    if not _MODEL_RE.match(payload.model):
        raise HTTPException(status_code=400, detail="invalid model name")
    node = (
        await session.execute(select(Node).where(Node.node_id == payload.node_id))
    ).scalar_one_or_none()
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")

    from app.schemas.task import TaskCreate
    from app.services import task_service

    task = await task_service.create_task(
        session,
        TaskCreate(
            title=f"Pull {payload.model} on {payload.node_id}",
            type="model_pull",
            required_capability=f"node:{payload.node_id}",
            payload={"model": payload.model},
        ),
    )
    return {"status": "queued", "task_id": task.id, "model": payload.model}
