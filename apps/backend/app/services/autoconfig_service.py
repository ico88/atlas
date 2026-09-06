"""Auto-configuration: make a pulled model "just work" (guided setup).

The multi-runtime registries (runtimes, deployments, aliases) are powerful but
too much to fill in by hand. This service does it for the user: after a model is
installed it ensures a local Ollama runtime, a deployment for that model, points
the ``atlas.general`` alias at it, and sets it as the default — so chat routes to
it with no manual steps. Everything is idempotent.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import get_sessionmaker
from app.models.provider import LLMModel
from app.models.runtime import ModelDeployment, Runtime
from app.services import recommend_service, runtime_service, settings_service

logger = logging.getLogger(__name__)

_LOCAL_RUNTIME = "local-ollama"
_DEFAULT_ALIAS = "atlas.general"


async def ensure_local_ollama_runtime(session: AsyncSession) -> Runtime:
    """Return the auto-managed local Ollama runtime, creating it if needed."""

    runtime = await runtime_service.get_runtime_by_name(session, _LOCAL_RUNTIME)
    if runtime is not None:
        return runtime
    settings = await settings_service.get_effective_settings()
    return await runtime_service.create_runtime(
        session,
        name=_LOCAL_RUNTIME,
        runtime_type="ollama",
        endpoint=settings.ollama_url or get_settings().ollama_url,
        supports_streaming=True,
        max_concurrency=1,
        meta={"managed": True},
    )


def _capabilities_for(model_name: str) -> dict[str, bool]:
    """Best-effort default capabilities from the catalog (fallback: CHAT)."""

    for entry in recommend_service.CATALOG:
        if entry["model"] == model_name:
            return {c: True for c in entry["capabilities"]}
    if model_name == recommend_service._EMBEDDING["model"]:
        return {"EMBEDDINGS": True}
    return {"CHAT": True}


async def activate_model(session: AsyncSession, model_name: str) -> dict:
    """Wire a model end-to-end and make it the active default. Idempotent."""

    runtime = await ensure_local_ollama_runtime(session)

    # 1) Ensure the model registry row carries a model_key + capabilities.
    llm = (
        await session.execute(
            select(LLMModel).where(
                LLMModel.provider == "ollama", LLMModel.name == model_name
            )
        )
    ).scalar_one_or_none()
    if llm is None:
        llm = LLMModel(provider="ollama", name=model_name, available=True)
        session.add(llm)
    llm.model_key = model_name
    if not llm.capabilities:
        llm.capabilities = _capabilities_for(model_name)
    await session.commit()

    # 2) Ensure a deployment for this model on the local runtime.
    existing = (
        await session.execute(
            select(ModelDeployment).where(
                ModelDeployment.model_key == model_name,
                ModelDeployment.runtime_id == runtime.id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        await runtime_service.create_deployment(
            session,
            model_key=model_name,
            runtime_id=runtime.id,
            runtime_model_name=model_name,
            priority=100,
            max_concurrency=1,
            load_policy="ALWAYS_LOADED",
        )

    # 3) Point the default alias at it and set the default model.
    await runtime_service.upsert_alias(
        session,
        alias=_DEFAULT_ALIAS,
        targets=[model_name],
        description="Modello generale predefinito (auto-configurato).",
        enabled=True,
    )
    await settings_service.set_ai_config({"default_model": model_name})

    logger.info(
        "model auto-configured and activated",
        extra={"event": "autoconfig_activate", "context": {"model": model_name}},
    )
    return {"activated": model_name, "runtime": runtime.name, "alias": _DEFAULT_ALIAS}


async def autoconfigure_after_pull(model_name: str) -> None:
    """Entry point for the pull worker: open a session and activate the model.

    Embedding models are wired (deployment) but never made the chat default.
    Never raises — auto-config is a convenience, not a hard dependency.
    """

    try:
        async with get_sessionmaker()() as session:
            if model_name == recommend_service._EMBEDDING["model"]:
                runtime = await ensure_local_ollama_runtime(session)
                existing = (
                    await session.execute(
                        select(ModelDeployment).where(
                            ModelDeployment.model_key == model_name,
                            ModelDeployment.runtime_id == runtime.id,
                        )
                    )
                ).scalar_one_or_none()
                if existing is None:
                    await runtime_service.create_deployment(
                        session,
                        model_key=model_name,
                        runtime_id=runtime.id,
                        runtime_model_name=model_name,
                        load_policy="PINNED",
                    )
                return
            await activate_model(session, model_name)
    except Exception:  # noqa: BLE001 - convenience must never break the pull flow
        logger.exception("auto-configuration failed", extra={"event": "autoconfig_error"})
