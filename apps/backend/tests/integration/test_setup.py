"""Guided setup + auto-configuration (make it easy)."""

from __future__ import annotations

import pytest
from app.models.provider import LLMModel
from app.models.runtime import ModelAlias, ModelDeployment, Runtime
from app.services import autoconfig_service, recommend_service, settings_service
from sqlalchemy import select


# --------------------------------------------------------------------------- #
# Recommendation (pure)
# --------------------------------------------------------------------------- #
def test_recommend_gpu_gets_strong_model():
    hw = {"ram_total_mb": 32000, "gpu": {"count": 1, "devices": [{"vram_mb": 12000}]}}
    reco = recommend_service.recommend_models(hw)
    assert reco["primary"]["model"] == "qwen2.5:7b"
    assert reco["detected"]["has_gpu"] is True


def test_recommend_modest_cpu_gets_small_model():
    hw = {"ram_total_mb": 8000, "gpu": {"count": 0, "devices": []}}
    reco = recommend_service.recommend_models(hw)
    assert reco["primary"]["model"] in ("qwen2.5:3b", "llama3.2:3b")


def test_recommend_tiny_box_falls_back_to_smallest():
    hw = {"ram_total_mb": 2000, "gpu": {"count": 0, "devices": []}}
    reco = recommend_service.recommend_models(hw)
    assert reco["primary"]["model"] == "llama3.2:1b"


# --------------------------------------------------------------------------- #
# Auto-configuration
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_activate_model_wires_everything(session):
    result = await autoconfig_service.activate_model(session, "qwen2.5:3b")
    assert result["activated"] == "qwen2.5:3b"

    # Local runtime created.
    rt = (
        await session.execute(select(Runtime).where(Runtime.name == "local-ollama"))
    ).scalar_one_or_none()
    assert rt is not None and rt.runtime_type == "ollama"

    # Deployment created for the model on that runtime.
    dep = (
        await session.execute(
            select(ModelDeployment).where(ModelDeployment.model_key == "qwen2.5:3b")
        )
    ).scalar_one_or_none()
    assert dep is not None and dep.runtime_id == rt.id

    # Model row carries a key + capabilities.
    llm = (
        await session.execute(select(LLMModel).where(LLMModel.name == "qwen2.5:3b"))
    ).scalar_one()
    assert llm.model_key == "qwen2.5:3b"
    assert (llm.capabilities or {}).get("CHAT") is True

    # Default alias points at it + default model set.
    alias = (
        await session.execute(select(ModelAlias).where(ModelAlias.alias == "atlas.general"))
    ).scalar_one()
    assert alias.targets == ["qwen2.5:3b"]
    cfg = await settings_service.get_ai_config_public()
    assert cfg.get("default_model") == "qwen2.5:3b"


@pytest.mark.asyncio
async def test_activate_is_idempotent(session):
    await autoconfig_service.activate_model(session, "qwen2.5:3b")
    await autoconfig_service.activate_model(session, "qwen2.5:3b")
    deps = (
        await session.execute(
            select(ModelDeployment).where(ModelDeployment.model_key == "qwen2.5:3b")
        )
    ).scalars().all()
    assert len(deps) == 1  # not duplicated on the second call


@pytest.mark.asyncio
async def test_activate_switches_default(session):
    await autoconfig_service.activate_model(session, "qwen2.5:3b")
    await autoconfig_service.activate_model(session, "llama3.2:3b")
    alias = (
        await session.execute(select(ModelAlias).where(ModelAlias.alias == "atlas.general"))
    ).scalar_one()
    assert alias.targets == ["llama3.2:3b"]  # alias now points at the new model


# --------------------------------------------------------------------------- #
# Setup API
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_setup_status_shape(client):
    r = await client.get("/api/v1/setup/status")
    assert r.status_code == 200
    body = r.json()
    assert "hardware" in body and "recommendation" in body
    assert "primary" in body["recommendation"]
    assert "ollama_ready" in body and "configured" in body


@pytest.mark.asyncio
async def test_setup_activate_endpoint(client):
    r = await client.post("/api/v1/setup/activate", json={"model": "qwen2.5:3b"})
    assert r.status_code == 200
    assert r.json()["activated"] == "qwen2.5:3b"
    # It is now the configured/active model.
    status = (await client.get("/api/v1/setup/status")).json()
    assert status["active_model"] == "qwen2.5:3b"
    assert status["configured"] is True
