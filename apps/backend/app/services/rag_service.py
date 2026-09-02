"""RAG engine: ingestion, indexing and retrieval with citations (spec §6, M8)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.rag import Document, DocumentChunk, KnowledgeBase
from app.rag.chunking import chunk_text
from app.rag.embeddings import cosine_similarity, get_embedder

logger = logging.getLogger(__name__)


@dataclass
class RetrievalHit:
    chunk_id: str
    document_id: str
    document_title: str
    source: str | None
    chunk_index: int
    content: str
    score: float


async def create_kb(
    session: AsyncSession, *, name: str, description: str | None = None
) -> KnowledgeBase:
    existing = (
        await session.execute(select(KnowledgeBase).where(KnowledgeBase.name == name))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    kb = KnowledgeBase(name=name, description=description)
    session.add(kb)
    await session.commit()
    await session.refresh(kb)
    return kb


async def list_kbs(session: AsyncSession) -> list[KnowledgeBase]:
    return list((await session.execute(select(KnowledgeBase))).scalars().all())


async def list_documents(session: AsyncSession, *, kb_id: str | None = None) -> list[Document]:
    query = select(Document).order_by(Document.created_at.desc())
    if kb_id:
        query = query.where(Document.kb_id == kb_id)
    return list((await session.execute(query)).scalars().all())


async def ingest_document(
    session: AsyncSession,
    *,
    title: str,
    content: str,
    kb_id: str | None = None,
    source: str | None = None,
    content_type: str = "text/plain",
    metadata: dict[str, Any] | None = None,
) -> Document:
    """Create a document, split it into chunks and embed each chunk."""

    document = Document(
        title=title,
        source=source,
        content_type=content_type,
        doc_metadata=metadata,
        kb_id=kb_id,
    )
    session.add(document)
    await session.flush()

    embedder = get_embedder()
    chunks = chunk_text(content)
    for idx, piece in enumerate(chunks):
        embedding = await embedder.embed(piece)
        session.add(
            DocumentChunk(
                document_id=document.id,
                kb_id=kb_id,
                chunk_index=idx,
                content=piece,
                embedding=embedding,
            )
        )

    await session.commit()
    await session.refresh(document)
    logger.info(
        "document ingested",
        extra={
            "event": "rag_ingested",
            "context": {"document_id": document.id, "chunks": len(chunks)},
        },
    )
    return document


async def retrieve(
    session: AsyncSession,
    *,
    query: str,
    kb_id: str | None = None,
    top_k: int | None = None,
) -> list[RetrievalHit]:
    """Return the most similar chunks with their source citations."""

    top_k = top_k or get_settings().rag_top_k
    embedder = get_embedder()
    query_vec = await embedder.embed(query)

    stmt = select(DocumentChunk)
    if kb_id:
        stmt = stmt.where(DocumentChunk.kb_id == kb_id)
    chunks = list((await session.execute(stmt)).scalars().all())
    if not chunks:
        return []

    doc_ids = {c.document_id for c in chunks}
    docs = {
        d.id: d
        for d in (
            await session.execute(select(Document).where(Document.id.in_(doc_ids)))
        ).scalars()
    }

    scored: list[RetrievalHit] = []
    for chunk in chunks:
        if not chunk.embedding:
            continue
        score = cosine_similarity(query_vec, chunk.embedding)
        doc = docs.get(chunk.document_id)
        scored.append(
            RetrievalHit(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_title=doc.title if doc else "unknown",
                source=doc.source if doc else None,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                score=round(score, 4),
            )
        )

    scored.sort(key=lambda h: h.score, reverse=True)
    return scored[:top_k]
