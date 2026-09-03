"""Memory engine (spec §6, §14) with lifecycle (ROADMAP PR 14).

Adds provenance (source/type/tags), retrieval that records usage, retention
(TTL + expiry + pruning), and pin/importance controls on top of the semantic
user/project/environment memory store.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.base import utcnow
from app.models.rag import Memory
from app.rag.embeddings import cosine_similarity, get_embedder

logger = logging.getLogger(__name__)


@dataclass
class MemoryHit:
    id: str
    content: str
    scope: str
    scope_id: str | None
    score: float
    source: str | None = None
    mem_type: str = "fact"
    tags: list[str] | None = None
    importance: int = 0
    pinned: bool = False


def _aware(dt: datetime, ref: datetime) -> datetime:
    if dt.tzinfo is None and ref.tzinfo is not None:
        return dt.replace(tzinfo=ref.tzinfo)
    if dt.tzinfo is not None and ref.tzinfo is None:
        return dt.replace(tzinfo=None)
    return dt


def is_expired(mem: Memory, *, now: datetime | None = None) -> bool:
    if mem.pinned or mem.expires_at is None:
        return False
    now = now or utcnow()
    return _aware(mem.expires_at, now) < now


async def add_memory(
    session: AsyncSession,
    *,
    content: str,
    scope: str = "user",
    scope_id: str | None = None,
    environment_id: str | None = None,
    source: str | None = None,
    source_id: str | None = None,
    mem_type: str = "fact",
    tags: list[str] | None = None,
    importance: int = 0,
    pinned: bool = False,
    ttl_seconds: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> Memory:
    embedding = await get_embedder().embed(content)
    ttl = ttl_seconds if ttl_seconds is not None else get_settings().memory_default_ttl_seconds
    expires_at = None
    if ttl and ttl > 0 and not pinned:
        expires_at = utcnow() + timedelta(seconds=ttl)
    memory = Memory(
        content=content,
        scope=scope,
        scope_id=scope_id,
        environment_id=environment_id,
        embedding=embedding,
        mem_metadata=metadata,
        source=source,
        source_id=source_id,
        mem_type=mem_type,
        tags=tags,
        importance=importance,
        pinned=pinned,
        expires_at=expires_at,
    )
    session.add(memory)
    await session.commit()
    await session.refresh(memory)
    logger.info(
        "memory stored",
        extra={
            "event": "memory_stored",
            "context": {"scope": scope, "source": source, "mem_type": mem_type},
        },
    )
    return memory


async def list_memories(
    session: AsyncSession,
    *,
    scope: str | None = None,
    scope_id: str | None = None,
    environment_id: str | None = None,
    source: str | None = None,
    include_expired: bool = False,
) -> list[Memory]:
    query = select(Memory).order_by(Memory.importance.desc(), Memory.created_at.desc())
    if scope:
        query = query.where(Memory.scope == scope)
    if scope_id:
        query = query.where(Memory.scope_id == scope_id)
    if environment_id:
        query = query.where(Memory.environment_id == environment_id)
    if source:
        query = query.where(Memory.source == source)
    rows = list((await session.execute(query)).scalars().all())
    if include_expired:
        return rows
    now = utcnow()
    return [m for m in rows if not is_expired(m, now=now)]


async def get_memory(session: AsyncSession, memory_id: str) -> Memory | None:
    return await session.get(Memory, memory_id)


async def search_memories(
    session: AsyncSession,
    *,
    query: str,
    scope: str | None = None,
    scope_id: str | None = None,
    environment_id: str | None = None,
    top_k: int | None = None,
    record_access: bool = True,
) -> list[MemoryHit]:
    top_k = top_k or get_settings().rag_top_k
    query_vec = await get_embedder().embed(query)
    memories = await list_memories(
        session, scope=scope, scope_id=scope_id, environment_id=environment_id
    )

    scored: list[tuple[float, Memory]] = []
    for mem in memories:
        if not mem.embedding:
            continue
        scored.append((round(cosine_similarity(query_vec, mem.embedding), 4), mem))
    # Tie-break by importance so pinned/important memories surface first.
    scored.sort(key=lambda t: (t[0], t[1].importance), reverse=True)
    top = scored[:top_k]

    if record_access and top:
        now = utcnow()
        for _score, mem in top:
            mem.access_count += 1
            mem.last_accessed_at = now
        await session.commit()

    return [
        MemoryHit(
            id=mem.id,
            content=mem.content,
            scope=mem.scope,
            scope_id=mem.scope_id,
            score=score,
            source=mem.source,
            mem_type=mem.mem_type,
            tags=mem.tags,
            importance=mem.importance,
            pinned=mem.pinned,
        )
        for score, mem in top
    ]


async def set_pinned(session: AsyncSession, mem: Memory, pinned: bool) -> Memory:
    mem.pinned = pinned
    if pinned:
        mem.expires_at = None  # pinned memories never expire
    await session.commit()
    await session.refresh(mem)
    return mem


async def set_importance(session: AsyncSession, mem: Memory, importance: int) -> Memory:
    mem.importance = importance
    await session.commit()
    await session.refresh(mem)
    return mem


async def prune_expired(session: AsyncSession, *, now: datetime | None = None) -> int:
    """Delete expired, non-pinned memories. Returns the number removed."""

    now = now or utcnow()
    candidates = list(
        (
            await session.execute(
                select(Memory).where(
                    Memory.pinned.is_(False), Memory.expires_at.is_not(None)
                )
            )
        )
        .scalars()
        .all()
    )
    stale = [m.id for m in candidates if is_expired(m, now=now)]
    if stale:
        await session.execute(delete(Memory).where(Memory.id.in_(stale)))
        await session.commit()
        logger.info(
            "pruned expired memories",
            extra={"event": "memory_pruned", "context": {"count": len(stale)}},
        )
    return len(stale)
