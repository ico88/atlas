"""Embeddings and similarity (spec §6, M8).

Default embedder is a dependency-free, deterministic **hashing** embedder: it
maps a bag of tokens into a fixed-dimension L2-normalized vector. This keeps the
whole RAG/memory pipeline working offline and makes tests hermetic. When
``use_ollama_embeddings`` is enabled and Ollama is reachable, real embeddings are
used instead (same interface).

Vectors are stored as JSON lists and similarity is computed in Python (cosine).
This is portable across PostgreSQL and SQLite; a pgvector-accelerated path can be
added later without changing callers.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

import httpx

from app.core.config import get_settings

_TOKEN = re.compile(r"[a-z0-9]+")


class Embedder(Protocol):
    async def embed(self, text: str) -> list[float]: ...


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


class HashingEmbedder:
    """Deterministic bag-of-words hashing embedder (offline)."""

    name = "hashing"

    def __init__(self, dim: int | None = None) -> None:
        self.dim = dim or get_settings().embedding_dim

    async def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in _tokenize(text):
            digest = hashlib.md5(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[idx] += sign
        return _normalize(vec)


class OllamaEmbedder:
    """Embeddings via an Ollama server (used only when explicitly enabled)."""

    name = "ollama"

    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self._base_url}/api/embeddings",
                json={"model": self._model, "prompt": text},
            )
            resp.raise_for_status()
            return _normalize(list(resp.json().get("embedding", [])))


def get_embedder() -> Embedder:
    settings = get_settings()
    if settings.use_ollama_embeddings and settings.ollama_url:
        return OllamaEmbedder(settings.ollama_url, settings.embedding_model)
    return HashingEmbedder(settings.embedding_dim)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity; assumes inputs may not be normalized."""

    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
