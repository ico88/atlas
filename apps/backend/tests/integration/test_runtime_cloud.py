"""Multi-runtime Fase 3 / M9: cloud adapters + routing policies + escalation."""

from __future__ import annotations

import pytest
from app.ai import gateway
from app.ai.anthropic import AnthropicAdapter, _split_system, parse_anthropic_sse
from app.ai.base import ChatMessage, RuntimeHealth, RuntimeState
from app.ai.echo import EchoProvider
from app.ai.openai_compat import OpenAICompatAdapter
from app.models.provider import LLMModel
from app.models.runtime import Runtime
from app.services import runtime_service


# --------------------------------------------------------------------------- #
# Cloud adapters (pure)
# --------------------------------------------------------------------------- #
def test_anthropic_sse_parsing():
    line = 'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Ciao"}}'
    assert parse_anthropic_sse(line) == "Ciao"
    assert parse_anthropic_sse('data: {"type":"message_start"}') is None
    assert parse_anthropic_sse("event: ping") is None
    assert parse_anthropic_sse("data: nope") is None


def test_anthropic_splits_system_prompt():
    msgs = [
        ChatMessage(role="system", content="be brief"),
        ChatMessage(role="user", content="hi"),
        ChatMessage(role="assistant", content="hello"),
    ]
    system, convo = _split_system(msgs)
    assert system == "be brief"
    assert [m["role"] for m in convo] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_anthropic_health_needs_key():
    assert (await AnthropicAdapter(None).health()).state == RuntimeState.DOWN
    assert (await AnthropicAdapter("sk-x").health()).state == RuntimeState.UP


def test_adapter_factory_cloud_types():
    openai_rt = Runtime(name="oai", runtime_type="openai", api_key="sk")
    anthropic_rt = Runtime(name="anth", runtime_type="anthropic", api_key="sk")
    assert isinstance(gateway.adapter_for(openai_rt), OpenAICompatAdapter)  # default endpoint
    assert isinstance(gateway.adapter_for(anthropic_rt), AnthropicAdapter)


# --------------------------------------------------------------------------- #
# Policy-driven routing + escalation
# --------------------------------------------------------------------------- #
async def _model(session, key, caps):
    session.add(LLMModel(provider="p", name=key, model_key=key, capabilities=caps))
    await session.commit()


@pytest.mark.asyncio
async def test_policy_routes_by_task_type(session, monkeypatch):
    monkeypatch.setattr(gateway, "adapter_for", lambda rt: EchoProvider())
    await _model(session, "coder", {"CHAT": True, "CODING": True})
    rt = await runtime_service.create_runtime(session, name="rt", runtime_type="echo")
    await runtime_service.create_deployment(
        session, model_key="coder", runtime_id=rt.id, runtime_model_name="coder"
    )
    await runtime_service.upsert_alias(
        session, alias="atlas.coding", targets=["coder"], description=None, enabled=True
    )
    await runtime_service.upsert_policy(
        session, task_type="coding", required_capabilities=["CODING"],
        preferred_alias="atlas.coding", privacy="LOCAL_PREFERRED", fallback=[],
        max_latency_ms=None, priority=100, enabled=True,
    )

    decision = await gateway.resolve_for_task(session, "coding")
    assert decision is not None
    assert decision.model == "coder"


@pytest.mark.asyncio
async def test_policy_escalates_local_to_cloud(session, monkeypatch):
    # Local runtime is DOWN; policy allows cloud -> escalate to the cloud alias.
    def _adapter(rt):
        if rt.runtime_type == "echo":
            class _Down(EchoProvider):
                async def health(self) -> RuntimeHealth:
                    return RuntimeHealth(RuntimeState.DOWN, "local down")
            return _Down()
        return EchoProvider()  # stand-in for a healthy cloud adapter

    monkeypatch.setattr(gateway, "adapter_for", _adapter)
    settings = gateway.get_settings()
    monkeypatch.setattr(settings, "routing_cloud_allowed", True, raising=False)

    await _model(session, "local-m", {"CHAT": True})
    await _model(session, "cloud-m", {"CHAT": True})
    local = await runtime_service.create_runtime(session, name="local", runtime_type="echo")
    cloud = await runtime_service.create_runtime(
        session, name="cloud", runtime_type="openai", api_key="sk", endpoint="http://x"
    )
    await runtime_service.create_deployment(
        session, model_key="local-m", runtime_id=local.id, runtime_model_name="local-m"
    )
    await runtime_service.create_deployment(
        session, model_key="cloud-m", runtime_id=cloud.id, runtime_model_name="gpt-x"
    )
    await runtime_service.upsert_alias(
        session, alias="atlas.local", targets=["local-m"], description=None, enabled=True
    )
    await runtime_service.upsert_alias(
        session, alias="atlas.cloud", targets=["cloud-m"], description=None, enabled=True
    )
    await runtime_service.upsert_policy(
        session, task_type="hard", required_capabilities=["CHAT"],
        preferred_alias="atlas.local", privacy="CLOUD_ALLOWED",
        fallback=["atlas.cloud"], max_latency_ms=None, priority=100, enabled=True,
    )

    decision = await gateway.resolve_for_task(session, "hard")
    assert decision is not None
    assert decision.runtime == "cloud"  # fell back from the DOWN local runtime


@pytest.mark.asyncio
async def test_policy_api_roundtrip(client):
    up = await client.put(
        "/api/v1/routing-policies",
        json={
            "task_type": "translation",
            "required_capabilities": ["TRANSLATION"],
            "preferred_alias": "atlas.general",
            "privacy": "LOCAL_ONLY",
        },
    )
    assert up.status_code == 200
    assert up.json()["privacy"] == "LOCAL_ONLY"
    lst = await client.get("/api/v1/routing-policies")
    assert lst.json()["total"] == 1
    dele = await client.delete("/api/v1/routing-policies/translation")
    assert dele.status_code == 200
    assert (await client.get("/api/v1/routing-policies")).json()["total"] == 0
