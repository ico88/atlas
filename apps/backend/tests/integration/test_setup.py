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


# --------------------------------------------------------------------------- #
# Guided node setup
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_setup_nodes_lists_and_recommends(client, session):
    from app.models.node import Node

    session.add(
        Node(
            node_id="worker-1",
            label="Casa",
            hardware={"cpu_cores": 8, "ram_total_mb": 16000, "gpu": {"count": 0, "devices": []}},
        )
    )
    await session.commit()

    r = await client.get("/api/v1/setup/nodes")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    node = body["nodes"][0]
    assert node["node_id"] == "worker-1"
    assert node["recommendation"]["primary"]["model"]  # recommended from its RAM
    assert node["attached_runtime"] is None


@pytest.mark.asyncio
async def test_setup_node_attach_wires_runtime_and_deployment(client, session):
    from app.models.node import Node
    from app.models.runtime import ModelDeployment, Runtime
    from sqlalchemy import select

    session.add(Node(node_id="worker-2", hardware={"ram_total_mb": 8000}))
    await session.commit()

    r = await client.post(
        "/api/v1/setup/nodes/attach",
        json={"node_id": "worker-2", "model": "qwen2.5:3b", "endpoint": "http://10.147.0.2:11434"},
    )
    assert r.status_code == 200
    assert r.json()["runtime"] == "node-worker-2"

    rt = (
        await session.execute(select(Runtime).where(Runtime.name == "node-worker-2"))
    ).scalar_one()
    assert rt.node_id == "worker-2" and rt.endpoint == "http://10.147.0.2:11434"
    dep = (
        await session.execute(
            select(ModelDeployment).where(ModelDeployment.runtime_id == rt.id)
        )
    ).scalar_one()
    assert dep.model_key == "qwen2.5:3b" and dep.node_id == "worker-2"


@pytest.mark.asyncio
async def test_setup_node_attach_missing_node(client):
    r = await client.post(
        "/api/v1/setup/nodes/attach",
        json={"node_id": "ghost", "model": "qwen2.5:3b", "endpoint": "http://x:11434"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_setup_node_pull_creates_pinned_task(client, session):
    from app.models.node import Node
    from app.models.task import Task
    from sqlalchemy import select as _select

    session.add(Node(node_id="worker-3", hardware={"ram_total_mb": 8000}))
    await session.commit()

    r = await client.post(
        "/api/v1/setup/nodes/pull", json={"node_id": "worker-3", "model": "qwen2.5:3b"}
    )
    assert r.status_code == 202
    task_id = r.json()["task_id"]
    task = (await session.execute(_select(Task).where(Task.id == task_id))).scalar_one()
    assert task.type == "model_pull"
    assert task.required_capability == "node:worker-3"
    assert task.payload == {"model": "qwen2.5:3b"}


@pytest.mark.asyncio
async def test_node_claims_its_pinned_task(session):
    """A model_pull pinned to a node is claimable by that node (synthetic cap)."""
    from app.models.node import Node
    from app.schemas.task import TaskCreate
    from app.services import node_service, task_service

    node = Node(node_id="worker-4", capabilities={})  # no declared capabilities
    session.add(node)
    await session.commit()
    await session.refresh(node)

    await task_service.create_task(
        session,
        TaskCreate(type="model_pull", required_capability="node:worker-4", payload={"model": "m"}),
    )
    claimed = await node_service.claim_task(session, node)
    assert claimed is not None
    assert claimed.type == "model_pull"


@pytest.mark.asyncio
async def test_task_progress_endpoint(client, session):
    from app.models.node import Node
    from app.models.task import Task, TaskStatus
    from sqlalchemy import select as _sel

    session.add(Node(node_id="worker-9", hardware={"ram_total_mb": 8000}))
    await session.commit()
    r = await client.post(
        "/api/v1/setup/nodes/pull", json={"node_id": "worker-9", "model": "qwen2.5:3b"}
    )
    task_id = r.json()["task_id"]
    # Mark it running so the node could be executing it.
    task = (await session.execute(_sel(Task).where(Task.id == task_id))).scalar_one()
    task.status = TaskStatus.RUNNING.value
    await session.commit()

    p = await client.post(
        f"/api/v1/tasks/{task_id}/progress", json={"percent": 42, "status": "pulling"}
    )
    assert p.status_code == 200
    got = await client.get(f"/api/v1/tasks/{task_id}")
    assert got.json()["checkpoint"]["progress"]["percent"] == 42
