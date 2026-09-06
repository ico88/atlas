"""Adaptive routing from evals (ROADMAP M10)."""

from __future__ import annotations

import pytest
from app.ai import gateway
from app.ai.echo import EchoProvider
from app.models.eval import EvalRun, EvalRunStatus, EvalSuite
from app.models.provider import LLMModel
from app.services import learning_service, runtime_service


async def _suite(session) -> str:
    suite = EvalSuite(name="s")
    session.add(suite)
    await session.flush()
    return suite.id


async def _run(session, suite_id, model, avg_quality, status=EvalRunStatus.COMPLETED):
    run = EvalRun(
        suite_id=suite_id, model=model, status=status.value,
        metrics={"avg_quality": avg_quality, "avg_safety": 1.0},
    )
    session.add(run)
    await session.commit()


@pytest.mark.asyncio
async def test_model_quality_uses_latest_completed(session):
    sid = await _suite(session)
    await _run(session, sid, "good", 0.9)
    await _run(session, sid, "bad", 0.3)
    await _run(session, sid, "pending", 0.99, status=EvalRunStatus.RUNNING)

    q = await learning_service.model_quality(session)
    assert q == {"good": 0.9, "bad": 0.3}  # RUNNING run excluded


@pytest.mark.asyncio
async def test_alias_suggestion_when_alternative_is_better(session):
    sid = await _suite(session)
    await _run(session, sid, "weak", 0.4)
    await _run(session, sid, "strong", 0.9)
    await runtime_service.upsert_alias(
        session, alias="atlas.general", targets=["weak", "strong"], description=None, enabled=True
    )

    sugg = await learning_service.alias_suggestions(session)
    assert len(sugg) == 1
    assert sugg[0]["current"] == "weak" and sugg[0]["suggested"] == "strong"


@pytest.mark.asyncio
async def test_gateway_prefers_higher_quality_model(session, monkeypatch):
    monkeypatch.setattr(gateway, "adapter_for", lambda rt: EchoProvider())
    for key in ("weak", "strong"):
        session.add(
            LLMModel(provider="local", name=key, model_key=key, capabilities={"CHAT": True})
        )
    await session.commit()
    sid = await _suite(session)
    await _run(session, sid, "weak", 0.2)
    await _run(session, sid, "strong", 0.95)

    rt = await runtime_service.create_runtime(session, name="rt", runtime_type="echo")
    # Same priority; quality should tip the choice to "strong".
    await runtime_service.create_deployment(
        session, model_key="weak", runtime_id=rt.id, runtime_model_name="weak", priority=100
    )
    await runtime_service.create_deployment(
        session, model_key="strong", runtime_id=rt.id, runtime_model_name="strong", priority=100
    )
    decision = await gateway.resolve(session, required_capabilities={"CHAT"})
    assert decision is not None
    assert decision.model == "strong"


@pytest.mark.asyncio
async def test_routing_quality_api(client):
    r = await client.get("/api/v1/routing/quality")
    assert r.status_code == 200
    body = r.json()
    assert "quality" in body and "suggestions" in body
