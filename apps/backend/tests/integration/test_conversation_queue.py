"""Conversation queue tests (ROADMAP PR 11): immediate/queue/merge/parallel."""

from __future__ import annotations

import pytest
from app.services import conversation_queue as cq


@pytest.mark.asyncio
async def test_immediate_send_when_idle():
    result = await cq.enqueue("c1", "hello")
    assert result["status"] == "dispatched"
    assert result["message"]["content"] == "hello"
    assert await cq.is_active("c1") is True
    assert result["pending"] == 0


@pytest.mark.asyncio
async def test_second_message_is_queued_while_busy():
    first = await cq.enqueue("c1", "one")
    assert first["status"] == "dispatched"
    second = await cq.enqueue("c1", "two")
    assert second["status"] == "queued"
    assert second["position"] == 1
    status = await cq.status("c1")
    assert status["pending"] == 1
    assert status["items"][0]["content"] == "two"


@pytest.mark.asyncio
async def test_merge_consecutive_pending_user_messages():
    await cq.enqueue("c1", "active")  # dispatched, holds the lock
    await cq.enqueue("c1", "queued-1")  # pending
    await cq.enqueue("c1", "queued-2")  # merged into queued-1
    status = await cq.status("c1")
    assert status["pending"] == 1
    merged = status["items"][0]
    assert merged["content"] == "queued-1\n\nqueued-2"
    assert merged["merged_count"] == 2


@pytest.mark.asyncio
async def test_no_merge_when_disabled():
    await cq.enqueue("c1", "active")
    await cq.enqueue("c1", "q1")
    await cq.enqueue("c1", "q2", merge=False)
    status = await cq.status("c1")
    assert status["pending"] == 2


@pytest.mark.asyncio
async def test_complete_dispatches_next():
    await cq.enqueue("c1", "first")   # dispatched
    await cq.enqueue("c1", "second")  # queued
    nxt = await cq.complete("c1")
    assert nxt is not None
    assert nxt["content"] == "second"
    assert await cq.is_active("c1") is True  # re-acquired for the next turn
    # Draining the last turn leaves the conversation idle.
    assert await cq.complete("c1") is None
    assert await cq.is_active("c1") is False


@pytest.mark.asyncio
async def test_parallel_limit_blocks_extra_conversations(monkeypatch):
    from app.core import config

    settings = config.get_settings()
    monkeypatch.setattr(settings, "conversation_max_parallel", 2, raising=False)

    a = await cq.enqueue("ca", "x")
    b = await cq.enqueue("cb", "y")
    c = await cq.enqueue("cc", "z")
    assert a["status"] == "dispatched"
    assert b["status"] == "dispatched"
    # Third distinct conversation has no global slot -> its message waits.
    assert c["status"] == "queued"
    assert await cq.is_active("cc") is False

    # Freeing one slot lets the third conversation start.
    await cq.complete("ca")
    started = await cq.dispatch_next("cc")
    assert started is not None
    assert started["content"] == "z"


@pytest.mark.asyncio
async def test_clear_resets_conversation():
    await cq.enqueue("c1", "active")
    await cq.enqueue("c1", "pending")
    await cq.clear("c1")
    status = await cq.status("c1")
    assert status["pending"] == 0
    assert status["active"] is False


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_api_enqueue_and_status(client):
    r1 = await client.post("/api/v1/conversations/conv-api/messages", json={"content": "hi"})
    assert r1.status_code == 200
    assert r1.json()["status"] == "dispatched"

    r2 = await client.post("/api/v1/conversations/conv-api/messages", json={"content": "again"})
    assert r2.json()["status"] == "queued"

    st = await client.get("/api/v1/conversations/conv-api/queue")
    assert st.status_code == 200
    assert st.json()["pending"] == 1
    assert st.json()["active"] is True

    done = await client.post("/api/v1/conversations/conv-api/queue/complete")
    assert done.status_code == 200
    assert done.json()["next"]["content"] == "again"
