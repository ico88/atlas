"""Shared pytest fixtures.

The suite is hermetic: it runs against a file-backed SQLite database and an
in-memory fake Redis, so no external services are required. Environment
variables are set *before* any application module is imported so the cached
settings/engine pick them up.
"""

from __future__ import annotations

import os

os.environ.setdefault("ATLAS_ENV", "test")
os.environ.setdefault("ATLAS_DATABASE_URL", "sqlite+aiosqlite:///./test_atlas.db")
os.environ.setdefault("ATLAS_REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ATLAS_WORKER_DUMMY_DURATION", "0.0")
# Deterministic, fast retries in tests.
os.environ.setdefault("ATLAS_RETRY_BACKOFF_BASE", "0")
os.environ.setdefault("ATLAS_RETRY_JITTER", "0")
# Deterministic, offline AI: no Ollama, no inter-token delay -> echo provider.
os.environ.setdefault("ATLAS_OLLAMA_URL", "")
os.environ.setdefault("ATLAS_CHAT_STREAM_DELAY", "0")

import fakeredis.aioredis  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from app import redis_client  # noqa: E402
from app.db import get_engine, get_sessionmaker  # noqa: E402
from app.models import Base  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402


@pytest.fixture(scope="session")
def fake_redis() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture(autouse=True)
def _patch_redis(fake_redis, monkeypatch):
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)


@pytest_asyncio.fixture(autouse=True)
async def _reset_state(fake_redis):
    """Fresh schema and empty queue for every test."""

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await fake_redis.flushall()
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def session():
    async with get_sessionmaker()() as s:
        yield s


@pytest_asyncio.fixture
async def client():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
