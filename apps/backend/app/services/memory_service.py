"""Memory engine: semantic user/project memories (spec §6, §14: memories)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
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


async def add_memory(
    session: AsyncSession,
    *,
    content: str,
    scope: str = "user",
    scope_id: str | None = None,
    environment_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Memory:
    embedding = await get_embedder().embed(content)
    memory = Memory(
        content=content,
        scope=scope,
        scope_id=scope_id,
        environment_id=environment_id,
        embedding=embedding,
        mem_metadata=metadata,
    )
    session.add(memory)
    await session.commit()
    await session.refresh(memory)
    logger.info(
        "memory stored",
        extra={"event": "memory_stored", "context": {"scope": scope, "scope_id": scope_id}},
    )
    return memory


async def list_memories(
    session: AsyncSession,
    *,
    scope: str | None = None,
    scope_id: str | None = None,
    environment_id: str | None = None,
) -> list[Memory]:
    query = select(Memory).order_by(Memory.created_at.desc())
    if scope:
        query = query.where(Memory.scope == scope)
    if scope_id:
        query = query.where(Memory.scope_id == scope_id)
    if environment_id:
        query = query.where(Memory.environment_id == environment_id)
    return list((await session.execute(query)).scalars().all())


async def search_memories(
    session: AsyncSession,
    *,
    query: str,
    scope: str | None = None,
    scope_id: str | None = None,
    environment_id: str | None = None,
    top_k: int | None = None,
) -> list[MemoryHit]:
    top_k = top_k or get_settings().rag_top_k
    query_vec = await get_embedder().embed(query)
    memories = await list_memories(
        session, scope=scope, scope_id=scope_id, environment_id=environment_id
    )

    hits: list[MemoryHit] = []
    for mem in memories:
        if not mem.embedding:
            continue
        hits.append(
            MemoryHit(
                id=mem.id,
                content=mem.content,
                scope=mem.scope,
                scope_id=mem.scope_id,
                score=round(cosine_similarity(query_vec, mem.embedding), 4),
            )
        )
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:top_k]
