"""Multi-runtime Fase 2: circuit breaker + benchmarking."""

from __future__ import annotations

import pytest
from app.ai import circuit, gateway
from app.ai.base import RuntimeHealth, RuntimeState
from app.ai.echo import EchoProvider
from app.models.provider import LLMModel
from app.services import benchmark_service, runtime_service


def test_should_open_pure():
    assert circuit.should_open(5, 5) is True
    assert circuit.should_open(4, 5) is False
    assert circuit.should_open(9, 0) is False  # threshold 0 disables the breaker


@pytest.mark.asyncio
async def test_circuit_opens_and_recovers(monkeypatch):
    settings = circuit.get_settings()
    monkeypatch.setattr(settings, "runtime_circuit_threshold", 2, raising=False)
    monkeypatch.setattr(settings, "runtime_circuit_cooldown", 30.0, raising=False)

    assert await circuit.is_open("rt") is False
    await circuit.record_failure("rt")
    assert await circuit.is_open("rt") is False  # 1 < threshold
    await circuit.record_failure("rt")
    assert await circuit.is_open("rt") is True  # tripped at 2
    assert await circuit.state("rt") == "OPEN"

    await circuit.record_success("rt")  # a good result closes it
    assert await circuit.is_open("rt") is False


@pytest.mark.asyncio
async def test_gateway_skips_open_circuit(session, monkeypatch):
    monkeypatch.setattr(gateway, "adapter_for", lambda rt: EchoProvider())
    m = LLMModel(provider="local", name="m", model_key="m", capabilities={"CHAT": True})
    session.add(m)
    await session.commit()
    good = await runtime_service.create_runtime(session, name="good", runtime_type="echo")
    bad = await runtime_service.create_runtime(session, name="bad", runtime_type="echo")
    await runtime_service.create_deployment(
        session, model_key="m", runtime_id=good.id, runtime_model_name="m", priority=10
    )
    await runtime_service.create_deployment(
        session, model_key="m", runtime_id=bad.id, runtime_model_name="m", priority=999
    )

    # Force "bad" (higher priority) open -> gateway routes to "good".
    monkeypatch.setattr(circuit, "is_open", lambda name, **kw: _open(name == "bad"))
    decision = await gateway.resolve(session, required_capabilities={"CHAT"})
    assert decision is not None
    assert decision.runtime == "good"


async def _open(value: bool) -> bool:  # tiny awaitable helper for the monkeypatch
    return value


@pytest.mark.asyncio
async def test_gateway_records_failure_on_down_runtime(session, monkeypatch):
    class _Down(EchoProvider):
        async def health(self) -> RuntimeHealth:
            return RuntimeHealth(RuntimeState.DOWN, "boom")

    monkeypatch.setattr(gateway, "adapter_for", lambda rt: _Down())
    m = LLMModel(provider="local", name="m", model_key="m", capabilities={"CHAT": True})
    session.add(m)
    await session.commit()
    rt = await runtime_service.create_runtime(session, name="downrt", runtime_type="echo")
    await runtime_service.create_deployment(
        session, model_key="m", runtime_id=rt.id, runtime_model_name="m"
    )

    assert await gateway.resolve(session, required_capabilities={"CHAT"}) is None
    # The DOWN probe was recorded as a failure against the breaker.
    from app import redis_client

    assert int(await redis_client.get_redis().get("atlas:cb:fail:downrt")) == 1


@pytest.mark.asyncio
async def test_benchmark_persists_tokens_per_second(session):
    rt = await runtime_service.create_runtime(session, name="echo-rt", runtime_type="echo")
    dep = await runtime_service.create_deployment(
        session, model_key="echo-local", runtime_id=rt.id, runtime_model_name="echo-local"
    )
    assert dep.estimated_tokens_per_second is None

    result = await benchmark_service.benchmark_deployment(session, dep, rt)
    assert result["ok"] is True
    assert result["tokens"] > 0
    await session.refresh(dep)
    assert dep.estimated_tokens_per_second is not None
    assert dep.last_benchmark is not None


@pytest.mark.asyncio
async def test_benchmark_api(client):
    r = await client.post("/api/v1/runtimes", json={"name": "b-rt", "runtime_type": "echo"})
    rid = r.json()["id"]
    d = await client.post(
        "/api/v1/model-deployments",
        json={"model_key": "echo-local", "runtime_id": rid, "runtime_model_name": "echo-local"},
    )
    did = d.json()["id"]
    bench = await client.post(f"/api/v1/model-deployments/{did}/benchmark")
    assert bench.status_code == 200
    assert bench.json()["ok"] is True
