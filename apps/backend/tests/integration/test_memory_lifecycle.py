"""Memory lifecycle tests (ROADMAP PR 14): provenance, retrieval, retention."""

from __future__ import annotations

from datetime import timedelta

import pytest
from app.models.base import utcnow
from app.services import memory_service


async def _expire(session, mem):
    mem.expires_at = utcnow() - timedelta(seconds=10)
    await session.commit()
    await session.refresh(mem)


@pytest.mark.asyncio
async def test_add_records_provenance_and_tags(session):
    mem = await memory_service.add_memory(
        session,
        content="user prefers dark mode",
        source="chat",
        source_id="msg-1",
        mem_type="preference",
        tags=["ui", "prefs"],
        importance=5,
    )
    assert mem.source == "chat"
    assert mem.mem_type == "preference"
    assert mem.tags == ["ui", "prefs"]
    assert mem.importance == 5
    assert mem.expires_at is None  # no ttl -> never expires


@pytest.mark.asyncio
async def test_ttl_sets_expiry_but_pinned_does_not(session):
    m1 = await memory_service.add_memory(session, content="temp", ttl_seconds=3600)
    assert m1.expires_at is not None
    m2 = await memory_service.add_memory(session, content="perm", ttl_seconds=3600, pinned=True)
    assert m2.expires_at is None  # pinned ignores ttl


@pytest.mark.asyncio
async def test_list_excludes_expired_unless_requested(session):
    mem = await memory_service.add_memory(session, content="old", ttl_seconds=3600)
    await _expire(session, mem)

    assert await memory_service.list_memories(session) == []
    all_rows = await memory_service.list_memories(session, include_expired=True)
    assert len(all_rows) == 1


@pytest.mark.asyncio
async def test_search_records_access_and_skips_expired(session):
    live = await memory_service.add_memory(session, content="cats like naps", importance=1)
    stale = await memory_service.add_memory(session, content="cats like naps too", ttl_seconds=60)
    await _expire(session, stale)

    hits = await memory_service.search_memories(session, query="cats naps")
    assert [h.id for h in hits] == [live.id]  # expired excluded

    await session.refresh(live)
    assert live.access_count == 1
    assert live.last_accessed_at is not None


@pytest.mark.asyncio
async def test_prune_removes_expired_keeps_pinned(session):
    a = await memory_service.add_memory(session, content="a", ttl_seconds=60)
    b = await memory_service.add_memory(session, content="b", ttl_seconds=60)
    pinned = await memory_service.add_memory(session, content="p", ttl_seconds=60)
    await _expire(session, a)
    await _expire(session, b)
    # Pin then expire: pinned must survive pruning.
    await memory_service.set_pinned(session, pinned, True)
    pinned.expires_at = utcnow() - timedelta(seconds=10)
    await session.commit()

    removed = await memory_service.prune_expired(session)
    assert removed == 2
    remaining = await memory_service.list_memories(session, include_expired=True)
    assert {m.id for m in remaining} == {pinned.id}


@pytest.mark.asyncio
async def test_set_pinned_clears_expiry(session):
    mem = await memory_service.add_memory(session, content="x", ttl_seconds=60)
    assert mem.expires_at is not None
    await memory_service.set_pinned(session, mem, True)
    assert mem.pinned is True
    assert mem.expires_at is None


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_memory_api_provenance_pin_importance_prune(client):
    created = await client.post(
        "/api/v1/memories",
        json={
            "content": "prefers metric units",
            "source": "manual",
            "mem_type": "preference",
            "tags": ["units"],
            "importance": 3,
        },
    )
    assert created.status_code == 201
    mem = created.json()
    assert mem["source"] == "manual"
    assert mem["tags"] == ["units"]

    pinned = await client.post(f"/api/v1/memories/{mem['id']}/pin", json={"pinned": True})
    assert pinned.status_code == 200 and pinned.json()["pinned"] is True

    imp = await client.post(
        f"/api/v1/memories/{mem['id']}/importance", json={"importance": 9}
    )
    assert imp.json()["importance"] == 9

    search = await client.post("/api/v1/memories/search", json={"query": "metric units"})
    assert search.status_code == 200
    assert search.json()[0]["source"] == "manual"

    prune = await client.post("/api/v1/memories/prune")
    assert prune.status_code == 200
    assert prune.json()["pruned"] == 0  # the only memory is pinned


@pytest.mark.asyncio
async def test_pin_unknown_memory_404(client):
    resp = await client.post("/api/v1/memories/nope/pin", json={"pinned": True})
    assert resp.status_code == 404
