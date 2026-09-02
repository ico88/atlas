"""Query lifecycle tests (ROADMAP PR 10): persist, run, cancel, recover."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from app.ai.base import ChatMessage
from app.ai.router import RoutingDecision
from app.models.base import utcnow
from app.models.query import QueryStatus
from app.services import query_service


@pytest.mark.asyncio
async def test_create_and_run_completes(session):
    query = await query_service.create_query(session, prompt="hello world")
    assert query.status == QueryStatus.PENDING.value

    await query_service.run_query(query.id)

    refreshed = await query_service.get_query(session, query.id)
    await session.refresh(refreshed)
    assert refreshed.status == QueryStatus.COMPLETED.value
    assert "hello world" in (refreshed.result or "")
    assert refreshed.provider == "echo"
    assert refreshed.completed_at is not None


@pytest.mark.asyncio
async def test_cancel_before_start(session):
    query = await query_service.create_query(session, prompt="cancel me")
    cancelled = await query_service.request_cancel(session, query.id)
    assert cancelled.status == QueryStatus.CANCELLED.value

    # Running a query already cancelled is a no-op.
    await query_service.run_query(query.id)
    await session.refresh(cancelled)
    assert cancelled.status == QueryStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_cancel_during_run_saves_partial(session, monkeypatch):
    query = await query_service.create_query(session, prompt="stream then stop")

    async def _streamer(messages: list[ChatMessage], model: str) -> AsyncIterator[str]:
        yield "first "
        # Request cancellation mid-stream (as a concurrent cancel call would).
        await query_service._cancel_flag_set(query.id)
        yield "second "
        yield "third "

    class _Provider:
        name = "fake"

        def stream_chat(self, messages, model):
            return _streamer(messages, model)

    async def _select(mode="AUTO", requested_model=None):
        return RoutingDecision(_Provider(), "fake-model", reason="test")

    monkeypatch.setattr(query_service.router, "select", _select)

    await query_service.run_query(query.id, heartbeat_every=1)

    refreshed = await query_service.get_query(session, query.id)
    await session.refresh(refreshed)
    assert refreshed.status == QueryStatus.CANCELLED.value
    assert refreshed.result == "first "  # partial result preserved


@pytest.mark.asyncio
async def test_recover_stale_requeues_running(session):
    query = await query_service.create_query(session, prompt="orphan")
    # Simulate a crash mid-run: RUNNING with a stale heartbeat.
    query.status = QueryStatus.RUNNING.value
    query.started_at = utcnow() - timedelta(minutes=5)
    query.heartbeat_at = utcnow() - timedelta(minutes=5)
    await session.commit()

    recovered = await query_service.recover_stale(session, stale_after_seconds=0)
    assert query.id in recovered

    await session.refresh(query)
    assert query.status == QueryStatus.PENDING.value
    assert query.started_at is None


@pytest.mark.asyncio
async def test_recover_stale_skips_fresh_heartbeat(session):
    query = await query_service.create_query(session, prompt="alive")
    query.status = QueryStatus.RUNNING.value
    query.heartbeat_at = utcnow()  # fresh
    await session.commit()

    recovered = await query_service.recover_stale(session, stale_after_seconds=60)
    assert query.id not in recovered
    await session.refresh(query)
    assert query.status == QueryStatus.RUNNING.value


@pytest.mark.asyncio
async def test_api_create_runs_in_background_and_records_events(client):
    resp = await client.post("/api/v1/queries", json={"prompt": "via api"})
    assert resp.status_code == 202
    query_id = resp.json()["id"]

    # Poll until the background task reaches a terminal state.
    for _ in range(200):
        detail = (await client.get(f"/api/v1/queries/{query_id}")).json()
        if detail["status"] in ("COMPLETED", "FAILED", "CANCELLED"):
            break
        await asyncio.sleep(0.01)

    assert detail["status"] == "COMPLETED"
    assert "via api" in detail["result"]
    event_types = {e["event_type"] for e in detail["events"]}
    assert {"created", "started", "completed"} <= event_types


@pytest.mark.asyncio
async def test_api_cancel_and_list(client, session):
    resp = await client.post("/api/v1/queries", json={"prompt": "to cancel"})
    query_id = resp.json()["id"]
    # Cancel immediately; may land before or after the background run finishes.
    cancel = await client.post(f"/api/v1/queries/{query_id}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["status"] in ("CANCELLED", "RUNNING", "COMPLETED")

    listing = (await client.get("/api/v1/queries")).json()
    assert listing["total"] >= 1
    assert any(item["id"] == query_id for item in listing["items"])


@pytest.mark.asyncio
async def test_cancel_unknown_query_404(client):
    resp = await client.post("/api/v1/queries/does-not-exist/cancel")
    assert resp.status_code == 404
