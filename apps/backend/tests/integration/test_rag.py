"""Integration tests for RAG, memory and feedback (M8)."""

from __future__ import annotations

import pytest

DB_DOC = {
    "title": "Database guide",
    "content": (
        "To configure the PostgreSQL database connection, set ATLAS_DATABASE_URL. "
        "The connection string uses the asyncpg driver. Redis is used for the queue."
    ),
}
COOKING_DOC = {
    "title": "Pasta recipe",
    "content": "Boil water, add salt, cook the pasta for ten minutes, then drain and serve.",
}


@pytest.mark.asyncio
async def test_ingest_and_retrieve_with_citations(client):
    kb = (await client.post("/api/v1/knowledge-bases", json={"name": "docs"})).json()
    await client.post("/api/v1/documents", json={**DB_DOC, "kb_id": kb["id"], "source": "db.md"})
    await client.post("/api/v1/documents", json={**COOKING_DOC, "kb_id": kb["id"]})

    result = await client.post(
        "/api/v1/rag/query",
        json={"query": "how to configure the database connection", "kb_id": kb["id"]},
    )
    assert result.status_code == 200
    hits = result.json()["hits"]
    assert len(hits) >= 1
    # The most relevant hit is from the database doc, with a citation.
    top = hits[0]
    assert top["document_title"] == "Database guide"
    assert top["source"] == "db.md"
    assert top["score"] > 0


@pytest.mark.asyncio
async def test_retrieve_empty_kb_returns_nothing(client):
    result = await client.post("/api/v1/rag/query", json={"query": "anything"})
    assert result.status_code == 200
    assert result.json()["hits"] == []


@pytest.mark.asyncio
async def test_documents_listed(client):
    await client.post("/api/v1/documents", json=DB_DOC)
    listing = await client.get("/api/v1/documents")
    assert listing.json()["total"] == 1


@pytest.mark.asyncio
async def test_memory_add_and_semantic_search(client):
    await client.post(
        "/api/v1/memories",
        json={"content": "The user prefers dark mode in the UI", "scope": "user", "scope_id": "u1"},
    )
    await client.post(
        "/api/v1/memories",
        json={"content": "The project deadline is next Friday", "scope": "user", "scope_id": "u1"},
    )

    hits = await client.post(
        "/api/v1/memories/search",
        json={"query": "what theme does the user like", "scope_id": "u1"},
    )
    assert hits.status_code == 200
    results = hits.json()
    assert results[0]["content"] == "The user prefers dark mode in the UI"


@pytest.mark.asyncio
async def test_feedback_capture(client):
    resp = await client.post(
        "/api/v1/feedback",
        json={"target_type": "message", "target_id": "m1", "rating": 1, "comment": "great"},
    )
    assert resp.status_code == 201
    listing = await client.get("/api/v1/feedback?target_id=m1")
    assert len(listing.json()) == 1
    assert listing.json()[0]["rating"] == 1

    # Thumbs-down (rating -1) on a message uses the same endpoint (the chat
    # 👎 posts here; a wrong path 404s as "not found").
    down = await client.post(
        "/api/v1/feedback",
        json={"target_type": "message", "target_id": "m2", "rating": -1},
    )
    assert down.status_code == 201
    assert down.json()["rating"] == -1
