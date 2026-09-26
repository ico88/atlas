"""Knowledge & RAG domain API — Query Processing, Document Ingestion, Memory.

Knowledge domain: RAG pipeline (retrieval-augmented generation), knowledge base
management, document ingestion, memory capture and search, semantic queries.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.query import (
    QueryCreate,
    QueryDetail,
    QueryEventRead,
    QueryList,
    QueryRead,
)
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
    MemoryImportanceUpdate,
    MemoryPinUpdate,
    MemoryRead,
    MemorySearch,
    RagQuery,
    RagResult,
)
from app.domains.knowledge import query as query_module
from app.services import feedback_service, memory_service, rag_service

router = APIRouter(tags=["knowledge"])

# ============================================================================
# Queries
# ============================================================================

query_router = APIRouter(prefix="/api/v1/queries", tags=["queries"])


@query_router.post("", response_model=QueryRead, status_code=202)
async def create_query(
    payload: QueryCreate,
    session: AsyncSession = Depends(get_session),
) -> QueryRead:
    """Create a query and start it in the background (returns immediately)."""
    q = await query_module.create_query(
        session,
        prompt=payload.prompt,
        mode=payload.mode.value,
        model=payload.model,
        conversation_id=payload.conversation_id,
        environment_id=payload.environment_id,
    )
    query_module.schedule_run(q.id)
    return QueryRead.model_validate(q)


@query_router.get("", response_model=QueryList)
async def list_queries(
    status: str | None = Query(default=None),
    environment_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> QueryList:
    items, total = await query_module.list_queries(
        session, status=status, environment_id=environment_id, limit=limit
    )
    return QueryList(items=[QueryRead.model_validate(q) for q in items], total=total)


@query_router.get("/{query_id}", response_model=QueryDetail)
async def get_query(
    query_id: str,
    session: AsyncSession = Depends(get_session),
) -> QueryDetail:
    q = await query_module.get_query_with_events(session, query_id)
    if q is None:
        raise HTTPException(status_code=404, detail="Query not found")
    detail = QueryDetail.model_validate(q)
    detail.events = [QueryEventRead.model_validate(e) for e in q.events]
    return detail


@query_router.post("/{query_id}/cancel", response_model=QueryRead)
async def cancel_query(
    query_id: str,
    session: AsyncSession = Depends(get_session),
) -> QueryRead:
    q = await query_module.request_cancel(session, query_id)
    if q is None:
        raise HTTPException(status_code=404, detail="Query not found")
    return QueryRead.model_validate(q)


# ============================================================================
# RAG - Knowledge Bases & Documents
# ============================================================================

rag_router = APIRouter(prefix="/api/v1", tags=["rag"])


@rag_router.post("/knowledge-bases", response_model=KnowledgeBaseRead, status_code=201)
async def create_kb(
    payload: KnowledgeBaseCreate,
    session: AsyncSession = Depends(get_session),
) -> KnowledgeBaseRead:
    kb = await rag_service.create_kb(session, name=payload.name, description=payload.description)
    return KnowledgeBaseRead.model_validate(kb)


@rag_router.get("/knowledge-bases", response_model=list[KnowledgeBaseRead])
async def list_kbs(session: AsyncSession = Depends(get_session)) -> list[KnowledgeBaseRead]:
    kbs = await rag_service.list_kbs(session)
    return [KnowledgeBaseRead.model_validate(k) for k in kbs]


@rag_router.post("/documents", response_model=DocumentRead, status_code=201)
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


@rag_router.get("/documents", response_model=DocumentList)
async def list_documents(
    kb_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> DocumentList:
    docs = await rag_service.list_documents(session, kb_id=kb_id)
    return DocumentList(items=[DocumentRead.model_validate(d) for d in docs], total=len(docs))


@rag_router.post("/rag/query", response_model=RagResult)
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


# ============================================================================
# RAG - Memory
# ============================================================================


@rag_router.post("/memory", response_model=MemoryRead, status_code=201)
async def capture_memory(
    payload: MemoryCreate,
    session: AsyncSession = Depends(get_session),
) -> MemoryRead:
    mem = await memory_service.capture(
        session,
        content=payload.content,
        conversation_id=payload.conversation_id,
        importance=payload.importance,
        tags=payload.tags,
    )
    return MemoryRead.model_validate(mem)


@rag_router.get("/memory", response_model=list[MemoryRead])
async def search_memory(
    query: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> list[MemoryRead]:
    results = await memory_service.search(session, query=query)
    return [MemoryRead.model_validate(m) for m in results]


@rag_router.get("/memory/{memory_id}", response_model=MemoryRead)
async def get_memory(
    memory_id: str,
    session: AsyncSession = Depends(get_session),
) -> MemoryRead:
    mem = await memory_service.get(session, memory_id)
    if mem is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return MemoryRead.model_validate(mem)


@rag_router.patch("/memory/{memory_id}/importance", response_model=MemoryRead)
async def update_memory_importance(
    memory_id: str,
    payload: MemoryImportanceUpdate,
    session: AsyncSession = Depends(get_session),
) -> MemoryRead:
    mem = await memory_service.update_importance(
        session, memory_id, importance=payload.importance
    )
    if mem is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return MemoryRead.model_validate(mem)


@rag_router.patch("/memory/{memory_id}/pin", response_model=MemoryRead)
async def update_memory_pin(
    memory_id: str,
    payload: MemoryPinUpdate,
    session: AsyncSession = Depends(get_session),
) -> MemoryRead:
    mem = await memory_service.update_pin(session, memory_id, pinned=payload.pinned)
    if mem is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return MemoryRead.model_validate(mem)


# ============================================================================
# Feedback
# ============================================================================


@rag_router.post("/feedback", response_model=FeedbackRead, status_code=201)
async def create_feedback(
    payload: FeedbackCreate,
    session: AsyncSession = Depends(get_session),
) -> FeedbackRead:
    feedback = await feedback_service.create_feedback(
        session,
        query_id=payload.query_id,
        rating=payload.rating,
        comment=payload.comment,
    )
    return FeedbackRead.model_validate(feedback)


# ============================================================================
# Aggregate all knowledge routers
# ============================================================================

router.include_router(query_router)
router.include_router(rag_router)
