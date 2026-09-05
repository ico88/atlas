"""Multi-runtime Fase 4: concurrency reservation, capacity routing, preemption."""

from __future__ import annotations

import pytest
from app.ai import gateway, reservation
from app.ai.echo import EchoProvider
from app.models.provider import LLMModel
from app.services import runtime_service


def test_can_admit_pure():
    assert reservation.can_admit(0, 1) is True
    assert reservation.can_admit(1, 1) is False
    assert reservation.can_admit(5, 0) is True  # 0 => unlimited


def test_should_preempt_pure():
    assert reservation.should_preempt(10, 5) is True
    assert reservation.should_preempt(5, 5) is False
    assert reservation.should_preempt(10, None) is False  # nothing running


@pytest.mark.asyncio
async def test_reservation_acquire_release_bounds():
    assert await reservation.acquire("d1", max_concurrency=1) is True
    assert await reservation.active("d1") == 1
    # Second acquire is refused at capacity 1.
    assert await reservation.acquire("d1", max_concurrency=1) is False
    await reservation.release("d1")
    assert await reservation.active("d1") == 0
    # Release never goes negative.
    await reservation.release("d1")
    assert await reservation.active("d1") == 0


@pytest.mark.asyncio
async def test_reservation_context_manager():
    async with reservation.Reservation("d2", max_concurrency=1) as r:
        assert r.ok is True
        assert await reservation.active("d2") == 1
    assert await reservation.active("d2") == 0


@pytest.mark.asyncio
async def test_gateway_skips_deployment_at_capacity(session, monkeypatch):
    monkeypatch.setattr(gateway, "adapter_for", lambda rt: EchoProvider())
    session.add(LLMModel(provider="p", name="m", model_key="m", capabilities={"CHAT": True}))
    await session.commit()
    rt = await runtime_service.create_runtime(session, name="rt", runtime_type="echo")
    busy = await runtime_service.create_deployment(
        session, model_key="m", runtime_id=rt.id, runtime_model_name="busy",
        priority=999, max_concurrency=1,
    )
    await runtime_service.create_deployment(
        session, model_key="m", runtime_id=rt.id, runtime_model_name="free",
        priority=10, max_concurrency=1,
    )
    # Fill the high-priority deployment's only slot.
    assert await reservation.acquire(busy.id, max_concurrency=1) is True

    decision = await gateway.resolve(session, required_capabilities={"CHAT"})
    assert decision is not None
    assert decision.model == "free"  # routed past the busy deployment
    await reservation.release(busy.id)


@pytest.mark.asyncio
async def test_warm_model_scores_higher(session, monkeypatch):
    monkeypatch.setattr(gateway, "adapter_for", lambda rt: EchoProvider())
    session.add(LLMModel(provider="p", name="m", model_key="m", capabilities={"CHAT": True}))
    await session.commit()
    rt = await runtime_service.create_runtime(session, name="rt", runtime_type="echo")
    # Same priority; one is PINNED (kept warm) so it should win.
    await runtime_service.create_deployment(
        session, model_key="m", runtime_id=rt.id, runtime_model_name="cold",
        priority=100, load_policy="ON_DEMAND",
    )
    await runtime_service.create_deployment(
        session, model_key="m", runtime_id=rt.id, runtime_model_name="warm",
        priority=100, load_policy="PINNED",
    )
    decision = await gateway.resolve(session, required_capabilities={"CHAT"})
    assert decision is not None
    assert decision.model == "warm"


@pytest.mark.asyncio
async def test_load_policy_persists_via_api(client):
    r = await client.post("/api/v1/runtimes", json={"name": "rt", "runtime_type": "echo"})
    rid = r.json()["id"]
    d = await client.post(
        "/api/v1/model-deployments",
        json={
            "model_key": "m",
            "runtime_id": rid,
            "runtime_model_name": "m",
            "load_policy": "ALWAYS_LOADED",
            "max_concurrency": 2,
        },
    )
    assert d.status_code == 201
    assert d.json()["load_policy"] == "ALWAYS_LOADED"
    assert d.json()["max_concurrency"] == 2
