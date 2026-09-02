"""Chat orchestration and conversation persistence (spec §7, §9, M2).

The streaming generator owns its own database session because it runs after the
HTTP handler returns (StreamingResponse), so it cannot rely on a request-scoped
session. Every user turn and assistant reply is persisted (cronologia).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai import router
from app.ai.base import ChatMessage
from app.db import get_sessionmaker
from app.models.base import utcnow
from app.models.conversation import Conversation, Message, MessageRole
from app.schemas.chat import ChatRequest
from app.services import webtools_service

logger = logging.getLogger(__name__)


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _format_web_context(citations: list[dict]) -> str:
    """Build a grounding system message from web citations (numbered for [n] cites)."""

    lines = [
        "You have web search results. Answer using them and cite sources as [n].",
        "If the results are irrelevant, say so.",
        "",
        "Web results:",
    ]
    for i, c in enumerate(citations, start=1):
        lines.append(f"[{i}] {c.get('title') or c.get('url')} — {c.get('url')}")
        snippet = (c.get("snippet") or "").strip()
        if snippet:
            lines.append(f"    {snippet}")
    return "\n".join(lines)


async def _web_search(payload: ChatRequest) -> tuple[list[dict], str | None]:
    """Run a web search for the turn. Returns (citations, note). Never raises."""

    try:
        result = await webtools_service.search(payload.content, fetch_bodies=True)
        citations = cast("list[dict]", result.get("citations") or [])
        return citations, None
    except webtools_service.WebToolsDisabled:
        return [], "web tools are disabled (set ATLAS_WEB_TOOLS_ENABLED=true)"
    except Exception as exc:  # noqa: BLE001 - web failure must not break chat
        logger.warning("web search failed: %s", exc, extra={"event": "chat_web_error"})
        return [], "web search failed"


async def list_conversations(session: AsyncSession) -> tuple[list[Conversation], int]:
    query = select(Conversation).order_by(Conversation.updated_at.desc())
    items = list((await session.execute(query)).scalars().all())
    total = int(
        (await session.execute(select(func.count()).select_from(Conversation))).scalar_one()
    )
    return items, total


async def get_conversation(session: AsyncSession, conversation_id: str) -> Conversation | None:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(selectinload(Conversation.messages))
    )
    return result.scalar_one_or_none()


async def _history(session: AsyncSession, conversation_id: str) -> list[ChatMessage]:
    rows = (
        await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
    ).scalars().all()
    return [ChatMessage(role=m.role, content=m.content) for m in rows]


async def stream_chat(payload: ChatRequest) -> AsyncIterator[str]:
    """Run one chat turn, streaming SSE events and persisting both messages."""

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        # 1) Resolve or create the conversation.
        conversation: Conversation | None = None
        if payload.conversation_id:
            conversation = await session.get(Conversation, payload.conversation_id)
            if conversation is None:
                yield _sse({"type": "error", "detail": "Conversation not found"})
                return
        if conversation is None:
            title = payload.content.strip()[:60] or "New conversation"
            conversation = Conversation(title=title, mode=payload.mode.value)
            session.add(conversation)
            await session.flush()

        # 2) Persist the user message.
        session.add(
            Message(
                conversation_id=conversation.id,
                role=MessageRole.USER.value,
                content=payload.content,
            )
        )
        await session.commit()

        history = await _history(session, conversation.id)

        # 2b) Optional web grounding (ROADMAP PR 15): search and prepend context.
        citations: list[dict] = []
        if payload.web:
            citations, note = await _web_search(payload)
            if citations:
                history = [
                    ChatMessage(role="system", content=_format_web_context(citations))
                ] + history
            yield _sse({"type": "citations", "citations": citations, "note": note})

        # 3) Route to a provider/model.
        decision = await router.select(mode=payload.mode.value, requested_model=payload.model)
        yield _sse(
            {
                "type": "start",
                "conversation_id": conversation.id,
                "provider": decision.provider.name,
                "model": decision.model,
            }
        )

        # 4) Stream the reply, accumulating the full text.
        started = time.perf_counter()
        parts: list[str] = []
        try:
            async for piece in decision.provider.stream_chat(history, decision.model):
                parts.append(piece)
                yield _sse({"type": "token", "content": piece})
        except Exception as exc:  # noqa: BLE001 - surface provider errors to client
            logger.exception("chat stream failed", extra={"event": "chat_stream_error"})
            yield _sse({"type": "error", "detail": str(exc)})
            return

        latency_ms = int((time.perf_counter() - started) * 1000)
        full = "".join(parts).strip()

        # 5) Persist the assistant message.
        assistant = Message(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT.value,
            content=full,
            model=decision.model,
            provider=decision.provider.name,
            latency_ms=latency_ms,
            citations=citations or None,
        )
        session.add(assistant)
        conversation.updated_at = utcnow()  # bump ordering in the sidebar
        await session.commit()
        await session.refresh(assistant)

        yield _sse(
            {
                "type": "done",
                "conversation_id": conversation.id,
                "message_id": assistant.id,
                "latency_ms": latency_ms,
            }
        )
