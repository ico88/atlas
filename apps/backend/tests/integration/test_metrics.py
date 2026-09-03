"""Resource telemetry tests (ROADMAP PR 12): ingest, history, perf, retention."""

from __future__ import annotations

import pytest
from app.core.config import get_settings
from app.models.conversation import Conversation, Message, MessageRole
from app.schemas.node import NodeHeartbeat, NodeRegister
from app.services import metrics_service, node_service


@pytest.mark.asyncio
async def test_heartbeat_ingests_a_metric(session):
    await node_service.register_node(session, NodeRegister(node_id="n1"))
    node = await node_service.get_node_by_ref(session, "n1")
    await node_service.heartbeat(
        session, node, NodeHeartbeat(status="online", health={"load1": 1.5, "ram_free_mb": 2048})
    )
    rows = await metrics_service.history(session, "n1")
    assert len(rows) == 1
    assert rows[0].load1 == 1.5
    assert rows[0].ram_free_mb == 2048
    assert rows[0].data["load1"] == 1.5


@pytest.mark.asyncio
async def test_history_and_latest_per_node(session):
    for load in (0.1, 0.2, 0.3):
        await metrics_service.ingest_health(session, "na", {"load1": load})
    await metrics_service.ingest_health(session, "nb", {"load1": 9.9})

    hist = await metrics_service.history(session, "na", limit=10)
    assert len(hist) == 3
    assert hist[0].load1 == 0.3  # newest first

    latest = {m.node_id: m.load1 for m in await metrics_service.latest_per_node(session)}
    assert latest == {"na": 0.3, "nb": 9.9}


@pytest.mark.asyncio
async def test_retention_prunes_old_samples(session, monkeypatch):
    monkeypatch.setattr(get_settings(), "metrics_history_limit", 3, raising=False)
    for i in range(6):
        await metrics_service.ingest_health(session, "nc", {"load1": float(i)})
    rows = await metrics_service.history(session, "nc", limit=100)
    assert len(rows) == 3
    # The three most recent are kept (3,4,5).
    assert sorted(r.load1 for r in rows) == [3.0, 4.0, 5.0]


@pytest.mark.asyncio
async def test_ollama_perf_aggregates_message_latency(session):
    convo = Conversation(title="c")
    session.add(convo)
    await session.flush()
    for lat in (100, 200, 300):
        session.add(
            Message(
                conversation_id=convo.id,
                role=MessageRole.ASSISTANT.value,
                content="x",
                provider="ollama",
                model="llama3.2",
                latency_ms=lat,
            )
        )
    await session.commit()

    perf = await metrics_service.ollama_perf(session)
    assert len(perf) == 1
    row = perf[0]
    assert row["provider"] == "ollama"
    assert row["model"] == "llama3.2"
    assert row["count"] == 3
    assert row["avg_latency_ms"] == 200.0
    assert row["min_latency_ms"] == 100
    assert row["max_latency_ms"] == 300


@pytest.mark.asyncio
async def test_metrics_api_endpoints(client, session):
    await metrics_service.ingest_health(session, "api-node", {"load1": 0.42, "ram_free_mb": 512})

    latest = await client.get("/api/v1/metrics/nodes")
    assert latest.status_code == 200
    assert any(m["node_id"] == "api-node" for m in latest.json())

    hist = await client.get("/api/v1/metrics/nodes/api-node")
    assert hist.status_code == 200
    assert hist.json()["total"] == 1

    perf = await client.get("/api/v1/metrics/ollama")
    assert perf.status_code == 200
    assert "items" in perf.json()
