"""Chat orchestration and conversation persistence (spec §7, §9, M2).

The streaming generator owns its own database session because it runs after the
HTTP handler returns (StreamingResponse), so it cannot rely on a request-scoped
session. Every user turn and assistant reply is persisted (cronologia).
"""

from __future__ import annotations

import asyncio
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
from app.core.config import get_settings
from app.db import get_sessionmaker
from app.models.base import utcnow
from app.models.conversation import Conversation, Message, MessageRole
from app.rag.memory_capture import extract_facts
from app.schemas.chat import ChatRequest
from app.services import memory_service, webtools_service

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


async def _capture_memories(
    session: AsyncSession, content: str, user_id: str | None = None
) -> None:
    """Auto-save durable facts the user states (e.g. "sono Federico"). Best-effort.

    Memories are scoped to the authenticated user (scope_id=user_id) so each
    user's profile stays their own; in open mode (no user) they are unscoped.
    """

    if not get_settings().chat_memory_enabled:
        return
    facts = extract_facts(content)
    if not facts:
        return
    existing = {
        m.content.lower()
        for m in await memory_service.list_memories(session, scope="user", scope_id=user_id)
    }
    for fact in facts:
        if fact.lower() in existing:
            continue
        try:
            await memory_service.add_memory(
                session,
                content=fact,
                scope="user",
                scope_id=user_id,
                source="chat",
                mem_type="fact",
            )
        except Exception:  # noqa: BLE001 - memory is best-effort, never break chat
            logger.warning("auto memory capture failed", extra={"event": "mem_capture_error"})


async def _known_facts(session: AsyncSession, user_id: str | None = None) -> list[str]:
    """The small user 'profile' injected so the assistant remembers across chats."""

    if not get_settings().chat_memory_enabled:
        return []
    top_k = get_settings().chat_memory_top_k
    mems = await memory_service.list_memories(session, scope="user", scope_id=user_id)
    return [m.content for m in mems[:top_k]]


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


async def recover_pending_replies() -> int:
    """Fail any assistant replies left 'pending' by a crashed backend.

    A detached turn worker persists partial text as it streams; if the process
    dies mid-generation the row would otherwise stay 'pending' forever and the UI
    would show "working" indefinitely. On startup we mark such orphans as 'error'
    (keeping any partial text) so the user sees it was interrupted and can resend.
    Returns how many replies were recovered.
    """

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        rows = list(
            (
                await session.execute(
                    select(Message).where(
                        Message.role == MessageRole.ASSISTANT.value,
                        Message.status == "pending",
                    )
                )
            )
            .scalars()
            .all()
        )
        for m in rows:
            m.status = "error"
        if rows:
            await session.commit()
            logger.warning(
                "recovered interrupted chat replies",
                extra={"event": "chat_recover", "context": {"count": len(rows)}},
            )
        return len(rows)


async def list_conversations(
    session: AsyncSession,
    *,
    archived: bool = False,
    user_id: str | None = None,
    all_users: bool = False,
) -> tuple[list[Conversation], int]:
    """List conversations, scoped per user (ROADMAP PR 28).

    - ``all_users`` (admin): every conversation.
    - a ``user_id``: only that user's conversations.
    - otherwise (open mode / no auth): only unowned conversations — the
      single-operator's history.
    """

    conds = [Conversation.archived == archived]
    if not all_users:
        if user_id is not None:
            conds.append(Conversation.user_id == user_id)
        else:
            conds.append(Conversation.user_id.is_(None))
    query = select(Conversation).where(*conds).order_by(Conversation.updated_at.desc())
    items = list((await session.execute(query)).scalars().all())
    total = int(
        (
            await session.execute(select(func.count()).select_from(Conversation).where(*conds))
        ).scalar_one()
    )
    return items, total


async def set_archived(
    session: AsyncSession, conversation_id: str, archived: bool
) -> Conversation | None:
    """Archive/unarchive a conversation (hidden from the default list, kept)."""

    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        return None
    conversation.archived = archived
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def delete_conversation(session: AsyncSession, conversation_id: str) -> bool:
    """Delete a conversation and all its messages (content is erased)."""

    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        return False
    await session.delete(conversation)  # cascade removes its messages
    await session.commit()
    return True


async def get_conversation(session: AsyncSession, conversation_id: str) -> Conversation | None:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(selectinload(Conversation.messages))
    )
    return result.scalar_one_or_none()


async def _history(session: AsyncSession, conversation_id: str) -> list[ChatMessage]:
    """Recent conversation turns as model context.

    Only the last ``chat_history_limit`` messages are sent so latency stays flat
    as a conversation grows (0 = send everything).
    """

    limit = get_settings().chat_history_limit
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
    )
    if limit and limit > 0:
        stmt = stmt.limit(limit)
    rows = list((await session.execute(stmt)).scalars().all())
    rows.reverse()  # back to chronological order
    return [ChatMessage(role=m.role, content=m.content) for m in rows]


# Keep strong references to detached turn workers so they are not garbage
# collected mid-flight (see stream_chat).
_BACKGROUND_TURNS: set[asyncio.Task] = set()


async def _generate_anonymous_turn(payload: ChatRequest) -> AsyncIterator[dict]:
    """Anonymous mode (ROADMAP PR 28): a single turn that persists nothing.

    No conversation, no messages, no memory capture/recall — a clean, private
    reply. The web-grounding option still works for the turn itself.
    """

    history: list[ChatMessage] = []
    citations: list[dict] = []
    if payload.web:
        citations, note = await _web_search(payload)
        if citations:
            history = [ChatMessage(role="system", content=_format_web_context(citations))]
        yield {"type": "citations", "citations": citations, "note": note}
    history.append(ChatMessage(role="user", content=payload.content))

    decision = await router.select(mode=payload.mode.value, requested_model=payload.model)
    started = time.perf_counter()
    yield {
        "type": "start",
        "conversation_id": None,
        "message_id": None,
        "provider": decision.provider.name,
        "model": decision.model,
        "anonymous": True,
    }
    try:
        async for piece in decision.provider.stream_chat(history, decision.model):
            yield {"type": "token", "content": piece}
    except Exception as exc:  # noqa: BLE001 - surface provider errors to client
        logger.exception("anon chat stream failed", extra={"event": "chat_stream_error"})
        yield {"type": "error", "detail": str(exc)}
        return
    yield {
        "type": "done",
        "conversation_id": None,
        "message_id": None,
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }


async def _generate_turn(payload: ChatRequest, user_id: str | None = None) -> AsyncIterator[dict]:
    """Run one chat turn, yielding event dicts and persisting both messages.

    This owns its own DB session and does not depend on the HTTP request, so it
    runs to completion (persisting the assistant reply) even if the client that
    started it disconnects. When ``payload.anonymous`` is set, nothing is
    persisted (see :func:`_generate_anonymous_turn`).
    """

    if payload.anonymous:
        async for event in _generate_anonymous_turn(payload):
            yield event
        return

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        # 1) Resolve or create the conversation.
        conversation: Conversation | None = None
        if payload.conversation_id:
            conversation = await session.get(Conversation, payload.conversation_id)
            if conversation is None:
                yield {"type": "error", "detail": "Conversation not found"}
                return
        if conversation is None:
            title = payload.content.strip()[:60] or "New conversation"
            conversation = Conversation(
                title=title, mode=payload.mode.value, user_id=user_id
            )
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

        # 2a) Auto-capture durable facts ("sono Federico" -> remembered).
        await _capture_memories(session, payload.content, user_id)

        history = await _history(session, conversation.id)

        # 2b) Prepend known user facts so the assistant remembers across chats.
        facts = await _known_facts(session, user_id)
        if facts:
            profile = "Known facts about the user (use them when relevant):\n" + "\n".join(
                f"- {f}" for f in facts
            )
            history = [ChatMessage(role="system", content=profile)] + history

        # 2c) Optional web grounding (ROADMAP PR 15): search and prepend context.
        citations: list[dict] = []
        if payload.web:
            citations, note = await _web_search(payload)
            if citations:
                history = [
                    ChatMessage(role="system", content=_format_web_context(citations))
                ] + history
            yield {"type": "citations", "citations": citations, "note": note}

        # 3) Route to a provider/model.
        decision = await router.select(mode=payload.mode.value, requested_model=payload.model)

        # 3a) Persist the assistant reply up front as 'pending', so a client that
        #     reconnects (or reopens after closing the browser) can see and resume
        #     the in-flight reply instead of losing it.
        assistant = Message(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT.value,
            content="",
            status="pending",
            model=decision.model,
            provider=decision.provider.name,
            citations=citations or None,
        )
        session.add(assistant)
        conversation.updated_at = utcnow()  # bump ordering in the sidebar
        await session.commit()
        await session.refresh(assistant)

        yield {
            "type": "start",
            "conversation_id": conversation.id,
            "message_id": assistant.id,
            "provider": decision.provider.name,
            "model": decision.model,
        }

        # 4) Stream the reply, accumulating the full text. The partial text is
        #    flushed to the DB every ~0.8s so a client that reopens mid-generation
        #    sees the reply grow instead of a blank "working" bubble.
        started = time.perf_counter()
        last_flush = started
        parts: list[str] = []
        try:
            async for piece in decision.provider.stream_chat(history, decision.model):
                parts.append(piece)
                yield {"type": "token", "content": piece}
                now = time.perf_counter()
                if now - last_flush > 0.8:
                    assistant.content = "".join(parts)
                    await session.commit()
                    last_flush = now
        except Exception as exc:  # noqa: BLE001 - surface provider errors to client
            logger.exception("chat stream failed", extra={"event": "chat_stream_error"})
            assistant.content = "".join(parts)
            assistant.status = "error"
            await session.commit()
            yield {"type": "error", "detail": str(exc)}
            return

        latency_ms = int((time.perf_counter() - started) * 1000)

        # 5) Finalize the assistant message (same row -> 'complete').
        assistant.content = "".join(parts).strip()
        assistant.status = "complete"
        assistant.latency_ms = latency_ms
        assistant.citations = citations or None
        await session.commit()
        await session.refresh(assistant)

        yield {
            "type": "done",
            "conversation_id": conversation.id,
            "message_id": assistant.id,
            "latency_ms": latency_ms,
        }


async def _drive_turn(payload: ChatRequest, out: asyncio.Queue, user_id: str | None) -> None:
    """Background worker: run the turn to completion, pushing events to ``out``.

    Runs independently of the HTTP stream so that closing the browser does not
    interrupt generation — the assistant reply is persisted no matter what.
    """

    try:
        async for event in _generate_turn(payload, user_id):
            await out.put(event)
    except Exception as exc:  # noqa: BLE001 - never leave the reader hanging
        logger.exception("chat turn worker failed", extra={"event": "chat_turn_error"})
        await out.put({"type": "error", "detail": str(exc)})
    finally:
        await out.put(None)  # sentinel: stream complete


async def stream_chat(payload: ChatRequest, user_id: str | None = None) -> AsyncIterator[str]:
    """Stream a chat turn as SSE, backed by a detached worker.

    The generation happens in a background task that keeps running even if this
    HTTP stream is cancelled (client disconnect / browser close). The reader here
    just relays events; the worker owns persistence.
    """

    out: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(_drive_turn(payload, out, user_id))
    _BACKGROUND_TURNS.add(task)
    task.add_done_callback(_BACKGROUND_TURNS.discard)

    while True:
        event = await out.get()
        if event is None:
            break
        yield _sse(event)
