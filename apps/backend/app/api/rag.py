"""RAG, memory and feedback API (spec §6, §14, M8)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.rag import (
    Citation,
    DocumentCreate,
    DocumentList,
    DocumentRead,
    FeedbackCreate,
    FeedbackRead,
    KnowledgeBaseCreate,
    KnowledgeBaseRead,
    MemoryCreate,
    MemoryHitRead,
    MemoryRead,
    MemorySearch,
    RagQuery,
    RagResult,
)
from app.services import feedback_service, memory_service, rag_service

router = APIRouter(prefix="/api/v1", tags=["rag"])


# --- knowledge bases & documents ---

@router.post("/knowledge-bases", response_model=KnowledgeBaseRead, status_code=201)
async def create_kb(
    payload: KnowledgeBaseCreate,
    session: AsyncSession = Depends(get_session),
) -> KnowledgeBaseRead:
    kb = await rag_service.create_kb(session, name=payload.name, description=payload.description)
    return KnowledgeBaseRead.model_validate(kb)


@router.get("/knowledge-bases", response_model=list[KnowledgeBaseRead])
async def list_kbs(session: AsyncSession = Depends(get_session)) -> list[KnowledgeBaseRead]:
    kbs = await rag_service.list_kbs(session)
    return [KnowledgeBaseRead.model_validate(k) for k in kbs]


@router.post("/documents", response_model=DocumentRead, status_code=201)
async def ingest_document(
    payload: DocumentCreate,
    session: AsyncSession = Depends(get_session),
) -> DocumentRead:
    doc = await rag_service.ingest_document(
        session,
        title=payload.title,
        content=payload.content,
        kb_id=payload.kb_id,
        source=payload.source,
        content_type=payload.content_type,
        metadata=payload.metadata,
    )
    return DocumentRead.model_validate(doc)


@router.get("/documents", response_model=DocumentList)
async def list_documents(
    kb_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> DocumentList:
    docs = await rag_service.list_documents(session, kb_id=kb_id)
    return DocumentList(items=[DocumentRead.model_validate(d) for d in docs], total=len(docs))


@router.post("/rag/query", response_model=RagResult)
async def rag_query(
    payload: RagQuery,
    session: AsyncSession = Depends(get_session),
) -> RagResult:
    hits = await rag_service.retrieve(
        session, query=payload.query, kb_id=payload.kb_id, top_k=payload.top_k
    )
    return RagResult(
        query=payload.query,
        hits=[
            Citation(
                chunk_id=h.chunk_id,
                document_id=h.document_id,
                document_title=h.document_title,
                source=h.source,
                chunk_index=h.chunk_index,
                content=h.content,
                score=h.score,
            )
            for h in hits
        ],
    )


# --- memory ---

@router.post("/memories", response_model=MemoryRead, status_code=201)
async def add_memory(
    payload: MemoryCreate,
    session: AsyncSession = Depends(get_session),
) -> MemoryRead:
    mem = await memory_service.add_memory(
        session,
        content=payload.content,
        scope=payload.scope,
        scope_id=payload.scope_id,
        metadata=payload.metadata,
    )
    return MemoryRead.model_validate(mem)


@router.get("/memories", response_model=list[MemoryRead])
async def list_memories(
    scope: str | None = Query(default=None),
    scope_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[MemoryRead]:
    mems = await memory_service.list_memories(session, scope=scope, scope_id=scope_id)
    return [MemoryRead.model_validate(m) for m in mems]


@router.post("/memories/search", response_model=list[MemoryHitRead])
async def search_memories(
    payload: MemorySearch,
    session: AsyncSession = Depends(get_session),
) -> list[MemoryHitRead]:
    hits = await memory_service.search_memories(
        session,
        query=payload.query,
        scope=payload.scope,
        scope_id=payload.scope_id,
        top_k=payload.top_k,
    )
    return [
        MemoryHitRead(id=h.id, content=h.content, scope=h.scope, scope_id=h.scope_id, score=h.score)
        for h in hits
    ]


# --- feedback ---

@router.post("/feedback", response_model=FeedbackRead, status_code=201)
async def add_feedback(
    payload: FeedbackCreate,
    session: AsyncSession = Depends(get_session),
) -> FeedbackRead:
    fb = await feedback_service.add_feedback(
        session,
        target_type=payload.target_type,
        target_id=payload.target_id,
        rating=payload.rating,
        comment=payload.comment,
        user_id=payload.user_id,
    )
    return FeedbackRead.model_validate(fb)


@router.get("/feedback", response_model=list[FeedbackRead])
async def list_feedback(
    target_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[FeedbackRead]:
    items = await feedback_service.list_feedback(session, target_id=target_id)
    return [FeedbackRead.model_validate(f) for f in items]


# a 404 helper kept for symmetry with other routers
@router.get("/knowledge-bases/{kb_id}", response_model=KnowledgeBaseRead)
async def get_kb(
    kb_id: str,
    session: AsyncSession = Depends(get_session),
) -> KnowledgeBaseRead:
    for kb in await rag_service.list_kbs(session):
        if kb.id == kb_id:
            return KnowledgeBaseRead.model_validate(kb)
    raise HTTPException(status_code=404, detail="Knowledge base not found")
