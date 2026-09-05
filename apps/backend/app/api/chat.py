"""Chat and conversation API (spec §15, M2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user_optional
from app.db import get_session
from app.models.user import User
from app.schemas.chat import (
    ChatRequest,
    ConversationList,
    ConversationRead,
    ConversationSummary,
    MessageRead,
)
from app.services import chat_service

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    user: User | None = Depends(current_user_optional),
) -> StreamingResponse:
    """Stream a chat reply as Server-Sent Events (text/event-stream)."""

    return StreamingResponse(
        chat_service.stream_chat(payload, user_id=user.id if user else None),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class ArchiveRequest(BaseModel):
    archived: bool = True


@router.get("/conversations", response_model=ConversationList)
async def list_conversations(
    archived: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(current_user_optional),
) -> ConversationList:
    items, total = await chat_service.list_conversations(
        session,
        archived=archived,
        user_id=user.id if user else None,
        all_users=bool(user and user.role == "admin"),
    )
    return ConversationList(
        items=[ConversationSummary.model_validate(c) for c in items], total=total
    )


@router.post("/conversations/{conversation_id}/archive", response_model=ConversationSummary)
async def archive_conversation(
    conversation_id: str,
    payload: ArchiveRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> ConversationSummary:
    archived = payload.archived if payload is not None else True
    conversation = await chat_service.set_archived(session, conversation_id, archived)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationSummary.model_validate(conversation)


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
) -> Response:
    ok = await chat_service.delete_conversation(session, conversation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return Response(status_code=204)


@router.get("/conversations/{conversation_id}", response_model=ConversationRead)
async def get_conversation(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
) -> ConversationRead:
    conversation = await chat_service.get_conversation(session, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    result = ConversationRead.model_validate(conversation)
    result.messages = [MessageRead.model_validate(m) for m in conversation.messages]
    return result
