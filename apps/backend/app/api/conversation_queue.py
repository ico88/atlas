"""Conversation queue API (ROADMAP PR 11).

Immediate-send / queue / merge / parallel semantics for per-conversation
messages. Kept separate from ``/chat/stream`` (the live streamer) so callers can
manage back-pressure explicitly; see docs/CONVERSATION_QUEUE.md.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.conversation_queue import (
    CompleteResponse,
    EnqueueRequest,
    EnqueueResponse,
    QueueStatusResponse,
)
from app.services import conversation_queue

router = APIRouter(prefix="/api/v1/conversations", tags=["conversation-queue"])


@router.post("/{conversation_id}/messages", response_model=EnqueueResponse)
async def enqueue_message(conversation_id: str, payload: EnqueueRequest) -> EnqueueResponse:
    result = await conversation_queue.enqueue(
        conversation_id, payload.content, role=payload.role, merge=payload.merge
    )
    return EnqueueResponse.model_validate(result)


@router.get("/{conversation_id}/queue", response_model=QueueStatusResponse)
async def queue_status(conversation_id: str) -> QueueStatusResponse:
    return QueueStatusResponse.model_validate(await conversation_queue.status(conversation_id))


@router.post("/{conversation_id}/queue/complete", response_model=CompleteResponse)
async def complete_turn(conversation_id: str) -> CompleteResponse:
    """Mark the active turn complete and dispatch the next pending message."""

    nxt = await conversation_queue.complete(conversation_id)
    return CompleteResponse(conversation_id=conversation_id, next=nxt)
