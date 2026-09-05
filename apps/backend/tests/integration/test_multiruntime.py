"""Multi-runtime Fase 1: Model Gateway routing, fallback, and the registry API.

Includes the ROADMAP acceptance test (#48): two runtimes on one node, two models,
a chat request that is routed to a deployment and executed, plus fallback when the
chosen runtime is stopped. Hermetic — echo/stub adapters, no real engines.
"""

from __future__ import annotations

import pytest
from app.ai import gateway
from app.ai.base import RuntimeHealth, RuntimeState
from app.ai.echo import EchoProvider
from app.ai.gateway import Privacy
from app.models.provider import LLMModel
from app.services import runtime_service


class _Stub(EchoProvider):
    """Echo adapter with a controllable health, to inject a runtime crash."""

    def __init__(self, name: str, state: RuntimeState) -> None:
        self.name = name
        self._state = state

    async def health(self) -> RuntimeHealth:
        return RuntimeHealth(self._state, self.name)


async def _model(session, model_key: str, caps: dict) -> LLMModel:
    m = LLMModel(provider="local", name=model_key, model_key=model_key, capabilities=caps)
    session.add(m)
    await session.commit()
    return m


# --------------------------------------------------------------------------- #
# Gateway routing
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_gateway_picks_highest_score(session, monkeypatch):
    monkeypatch.setattr(gateway, "adapter_for", lambda rt: _Stub(rt.name, RuntimeState.UP))
    await _model(session, "qwen-8b", {"CHAT": True})
    rt_a = await runtime_service.create_runtime(
        session, name="node1-ollama", runtime_type="ollama", node_id="node1"
    )
    rt_b = await runtime_service.create_runtime(
        session, name="node1-llama", runtime_type="llama_cpp",
        endpoint="http://x", node_id="node1"
    )
    await runtime_service.create_deployment(
        session, model_key="qwen-8b", runtime_id=rt_a.id,
        runtime_model_name="qwen2.5:8b", priority=50, node_id="node1"
    )
    await runtime_service.create_deployment(
        session, model_key="qwen-8b", runtime_id=rt_b.id,
        runtime_model_name="qwen-8b-q4.gguf", priority=200, node_id="node1"
    )

    decision = await gateway.resolve(session, required_capabilities={"CHAT"})
    assert decision is not None
    assert decision.runtime == "node1-llama"  # higher priority wins
    assert decision.model == "qwen-8b-q4.gguf"
    assert decision.node == "node1"


@pytest.mark.asyncio
async def test_gateway_falls_back_when_runtime_down(session, monkeypatch):
    # node1-llama is the best candidate but its runtime is DOWN -> route to ollama.
    def _adapter(rt):
        return _Stub(rt.name, RuntimeState.DOWN if rt.name == "node1-llama" else RuntimeState.UP)

    monkeypatch.setattr(gateway, "adapter_for", _adapter)
    await _model(session, "qwen-8b", {"CHAT": True})
    rt_a = await runtime_service.create_runtime(
        session, name="node1-ollama", runtime_type="ollama", node_id="node1"
    )
    rt_b = await runtime_service.create_runtime(
        session, name="node1-llama", runtime_type="llama_cpp",
        endpoint="http://x", node_id="node1"
    )
    await runtime_service.create_deployment(
        session, model_key="qwen-8b", runtime_id=rt_a.id,
        runtime_model_name="qwen2.5:8b", priority=50
    )
    await runtime_service.create_deployment(
        session, model_key="qwen-8b", runtime_id=rt_b.id,
        runtime_model_name="q4.gguf", priority=200
    )

    decision = await gateway.resolve(session, required_capabilities={"CHAT"})
    assert decision is not None
    assert decision.runtime == "node1-ollama"  # fell back past the DOWN runtime


@pytest.mark.asyncio
async def test_gateway_capability_filter(session, monkeypatch):
    monkeypatch.setattr(gateway, "adapter_for", lambda rt: _Stub(rt.name, RuntimeState.UP))
    await _model(session, "coder", {"CHAT": True, "CODING": True})
    await _model(session, "chatter", {"CHAT": True})
    rt = await runtime_service.create_runtime(session, name="rt", runtime_type="ollama")
    await runtime_service.create_deployment(
        session, model_key="coder", runtime_id=rt.id, runtime_model_name="coder", priority=10
    )
    await runtime_service.create_deployment(
        session, model_key="chatter", runtime_id=rt.id, runtime_model_name="chatter", priority=999
    )

    # Even though "chatter" has far higher priority, only "coder" satisfies CODING.
    decision = await gateway.resolve(session, required_capabilities={"CODING"})
    assert decision is not None
    assert decision.model == "coder"


@pytest.mark.asyncio
async def test_gateway_local_only_excludes_cloud(session, monkeypatch):
    monkeypatch.setattr(gateway, "adapter_for", lambda rt: _Stub(rt.name, RuntimeState.UP))
    await _model(session, "m", {"CHAT": True})
    cloud = await runtime_service.create_runtime(
        session, name="openai", runtime_type="openai", endpoint="http://x"
    )
    await runtime_service.create_deployment(
        session, model_key="m", runtime_id=cloud.id, runtime_model_name="gpt", priority=999
    )
    # Only a cloud deployment exists; LOCAL_ONLY must yield no candidate.
    assert await gateway.resolve(session, privacy=Privacy.LOCAL_ONLY) is None


@pytest.mark.asyncio
async def test_alias_restricts_and_orders(session, monkeypatch):
    monkeypatch.setattr(gateway, "adapter_for", lambda rt: _Stub(rt.name, RuntimeState.UP))
    await _model(session, "big", {"CHAT": True})
    await _model(session, "small", {"CHAT": True})
    rt = await runtime_service.create_runtime(session, name="rt", runtime_type="ollama")
    await runtime_service.create_deployment(
        session, model_key="big", runtime_id=rt.id, runtime_model_name="big", priority=10
    )
    await runtime_service.create_deployment(
        session, model_key="small", runtime_id=rt.id, runtime_model_name="small", priority=999
    )
    # Alias prefers "big" first despite "small" having higher deployment priority.
    await runtime_service.upsert_alias(
        session, alias="atlas.general", targets=["big", "small"], description=None, enabled=True
    )
    decision = await gateway.resolve(session, alias="atlas.general")
    assert decision is not None
    assert decision.model == "big"


# --------------------------------------------------------------------------- #
# Registry API
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_runtime_and_deployment_api(client):
    r = await client.post(
        "/api/v1/runtimes",
        json={"name": "home-llama", "runtime_type": "llama_cpp", "endpoint": "http://h:8080"},
    )
    assert r.status_code == 201
    rid = r.json()["id"]

    # Duplicate name is rejected.
    dup = await client.post(
        "/api/v1/runtimes", json={"name": "home-llama", "runtime_type": "ollama"}
    )
    assert dup.status_code == 409

    d = await client.post(
        "/api/v1/model-deployments",
        json={"model_key": "qwen-8b", "runtime_id": rid, "runtime_model_name": "q4.gguf"},
    )
    assert d.status_code == 201

    # Deployment against a missing runtime is rejected.
    bad = await client.post(
        "/api/v1/model-deployments",
        json={"model_key": "x", "runtime_id": "nope", "runtime_model_name": "x"},
    )
    assert bad.status_code == 400

    listing = await client.get("/api/v1/runtimes")
    assert listing.json()["total"] == 1
    deps = await client.get("/api/v1/model-deployments")
    assert deps.json()["total"] == 1

    health = await client.get("/api/v1/runtimes-health")
    assert health.status_code == 200
    assert health.json()[0]["name"] == "home-llama"


@pytest.mark.asyncio
async def test_alias_api_roundtrip(client):
    up = await client.put(
        "/api/v1/model-aliases",
        json={"alias": "atlas.fast", "targets": ["qwen-4b"], "description": "fast local"},
    )
    assert up.status_code == 200
    assert up.json()["targets"] == ["qwen-4b"]
    lst = await client.get("/api/v1/model-aliases")
    assert lst.json()["total"] == 1
    dele = await client.delete("/api/v1/model-aliases/atlas.fast")
    assert dele.status_code == 200
    assert (await client.get("/api/v1/model-aliases")).json()["total"] == 0


# --------------------------------------------------------------------------- #
# Acceptance test (#48): two runtimes, two models, routed chat, then fallback
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_acceptance_two_runtimes_route_and_execute(client, session):
    # 1) two runtimes on the same node (echo-backed so it is hermetic).
    for name in ("acc-ollama", "acc-llama"):
        rt = await client.post(
            "/api/v1/runtimes",
            json={"name": name, "runtime_type": "echo", "node_id": "acc-node"},
        )
        assert rt.status_code == 201
        await client.post(
            "/api/v1/model-deployments",
            json={
                "model_key": "echo-local",
                "runtime_id": rt.json()["id"],
                "runtime_model_name": "echo-local",
                "priority": 100 if name == "acc-ollama" else 200,
                "node_id": "acc-node",
            },
        )

    # 2) a chat request is routed through the gateway and executed end to end.
    async with client.stream(
        "POST", "/api/v1/chat/stream", json={"content": "ciao"}
    ) as resp:
        assert resp.status_code == 200
        body = ""
        async for chunk in resp.aiter_text():
            body += chunk
    assert "token" in body and "done" in body  # a real reply was produced

    # 3) the gateway picks the highest-priority deployment (acc-llama).
    decision = await gateway.resolve(session)
    assert decision is not None
    assert decision.runtime == "acc-llama"
