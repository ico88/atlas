"""Unit tests for embeddings, chunking and similarity (M8)."""

from __future__ import annotations

import pytest
from app.rag.chunking import chunk_text
from app.rag.embeddings import HashingEmbedder, cosine_similarity


@pytest.mark.asyncio
async def test_hashing_embedder_is_deterministic_and_normalized():
    emb = HashingEmbedder(dim=128)
    a = await emb.embed("the quick brown fox")
    b = await emb.embed("the quick brown fox")
    assert a == b
    assert len(a) == 128
    assert abs(sum(x * x for x in a) - 1.0) < 1e-6  # L2 normalized


@pytest.mark.asyncio
async def test_similar_texts_score_higher():
    emb = HashingEmbedder(dim=256)
    q = await emb.embed("how do I configure the database connection")
    close = await emb.embed("configure the database connection string")
    far = await emb.embed("the weather today is sunny and warm")
    assert cosine_similarity(q, close) > cosine_similarity(q, far)


def test_cosine_edge_cases():
    assert cosine_similarity([], [1.0]) == 0.0
    assert cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0
    assert abs(cosine_similarity([1.0, 0.0], [1.0, 0.0]) - 1.0) < 1e-9


def test_chunking_overlaps_and_covers():
    text = "para one. " * 100  # ~1000 chars
    chunks = chunk_text(text, size=300, overlap=50)
    assert len(chunks) >= 3
    assert all(len(c) <= 320 for c in chunks)


def test_chunking_short_text_single_chunk():
    assert chunk_text("short", size=800) == ["short"]
    assert chunk_text("   ") == []
