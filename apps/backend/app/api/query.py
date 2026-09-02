"""Query lifecycle API (ROADMAP PR 10)."""

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
from app.services import query_service

router = APIRouter(prefix="/api/v1/queries", tags=["queries"])


@router.post("", response_model=QueryRead, status_code=202)
async def create_query(
    payload: QueryCreate,
    session: AsyncSession = Depends(get_session),
) -> QueryRead:
    """Create a query and start it in the background (returns immediately)."""

    query = await query_service.create_query(
        session,
        prompt=payload.prompt,
        mode=payload.mode.value,
        model=payload.model,
        conversation_id=payload.conversation_id,
    )
    query_service.schedule_run(query.id)
    return QueryRead.model_validate(query)


@router.get("", response_model=QueryList)
async def list_queries(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> QueryList:
    items, total = await query_service.list_queries(session, status=status, limit=limit)
    return QueryList(items=[QueryRead.model_validate(q) for q in items], total=total)


@router.get("/{query_id}", response_model=QueryDetail)
async def get_query(
    query_id: str,
    session: AsyncSession = Depends(get_session),
) -> QueryDetail:
    query = await query_service.get_query_with_events(session, query_id)
    if query is None:
        raise HTTPException(status_code=404, detail="Query not found")
    detail = QueryDetail.model_validate(query)
    detail.events = [QueryEventRead.model_validate(e) for e in query.events]
    return detail


@router.post("/{query_id}/cancel", response_model=QueryRead)
async def cancel_query(
    query_id: str,
    session: AsyncSession = Depends(get_session),
) -> QueryRead:
    query = await query_service.request_cancel(session, query_id)
    if query is None:
        raise HTTPException(status_code=404, detail="Query not found")
    return QueryRead.model_validate(query)
