"""Database engine and session management (async SQLAlchemy 2.0)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    """Return a cached async engine built from settings.

    ``NullPool`` is not required here; the default pool is fine for the control
    plane. SQLite (used by the hermetic test suite) needs ``check_same_thread``
    disabled, which the async driver handles via ``connect_args``.
    """

    settings = get_settings()
    url = settings.database_url
    connect_args: dict = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_async_engine(url, echo=False, future=True, connect_args=connect_args)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_engine(), expire_on_commit=False, class_=AsyncSession
    )


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a database session."""

    async with get_sessionmaker()() as session:
        yield session
