"""Chat and conversation API (spec §15, M2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
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
async def chat_stream(payload: ChatRequest) -> StreamingResponse:
    """Stream a chat reply as Server-Sent Events (text/event-stream)."""

    return StreamingResponse(
        chat_service.stream_chat(payload),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations", response_model=ConversationList)
async def list_conversations(
    session: AsyncSession = Depends(get_session),
) -> ConversationList:
    items, total = await chat_service.list_conversations(session)
    return ConversationList(
        items=[ConversationSummary.model_validate(c) for c in items], total=total
    )


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
