"""Integration tests for chat streaming + conversation history (M2)."""

from __future__ import annotations

import json

import pytest


def _parse_sse(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: ") :]))
    return events


@pytest.mark.asyncio
async def test_chat_stream_creates_conversation_and_history(client):
    async with client.stream(
        "POST", "/api/v1/chat/stream", json={"content": "hello there"}
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = ""
        async for chunk in resp.aiter_text():
            body += chunk

    events = _parse_sse(body)
    types = [e["type"] for e in events]
    assert types[0] == "start"
    assert "token" in types
    assert types[-1] == "done"

    start = events[0]
    assert start["provider"] == "echo"
    conversation_id = start["conversation_id"]

    # The conversation and both messages are persisted (cronologia).
    convo = await client.get(f"/api/v1/conversations/{conversation_id}")
    assert convo.status_code == 200
    data = convo.json()
    roles = [m["role"] for m in data["messages"]]
    assert roles == ["user", "assistant"]
    assert "hello there" in data["messages"][0]["content"]
    assert data["messages"][1]["provider"] == "echo"


@pytest.mark.asyncio
async def test_chat_continues_existing_conversation(client):
    async with client.stream("POST", "/api/v1/chat/stream", json={"content": "first"}) as r:
        body = "".join([c async for c in r.aiter_text()])
    conversation_id = _parse_sse(body)[0]["conversation_id"]

    async with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"content": "second", "conversation_id": conversation_id},
    ) as r:
        body2 = "".join([c async for c in r.aiter_text()])
    assert _parse_sse(body2)[0]["conversation_id"] == conversation_id

    convo = (await client.get(f"/api/v1/conversations/{conversation_id}")).json()
    assert len(convo["messages"]) == 4  # 2 user + 2 assistant


@pytest.mark.asyncio
async def test_list_conversations(client):
    async with client.stream("POST", "/api/v1/chat/stream", json={"content": "hi"}) as r:
        async for _ in r.aiter_text():
            pass
    listing = await client.get("/api/v1/conversations")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1


@pytest.mark.asyncio
async def test_chat_missing_conversation_errors(client):
    async with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"content": "x", "conversation_id": "does-not-exist"},
    ) as r:
        body = "".join([c async for c in r.aiter_text()])
    events = _parse_sse(body)
    assert events[-1]["type"] == "error"


@pytest.mark.asyncio
async def test_chat_web_disabled_emits_note_and_completes(client):
    """web=true with web tools disabled: a citations note is emitted, chat still finishes."""
    async with client.stream(
        "POST", "/api/v1/chat/stream", json={"content": "search this", "web": True}
    ) as r:
        body = "".join([c async for c in r.aiter_text()])
    events = _parse_sse(body)
    types = [e["type"] for e in events]
    assert "citations" in types
    citation_evt = next(e for e in events if e["type"] == "citations")
    assert citation_evt["citations"] == []
    assert "disabled" in (citation_evt.get("note") or "")
    assert types[-1] == "done"


@pytest.mark.asyncio
async def test_chat_auto_captures_user_name(client):
    """Saying "sono Federico" is remembered automatically as a user memory."""
    async with client.stream(
        "POST", "/api/v1/chat/stream", json={"content": "ciao, sono Federico"}
    ) as r:
        async for _ in r.aiter_text():
            pass
    mems = (await client.get("/api/v1/memories?scope=user")).json()
    assert any("Federico" in m["content"] for m in mems)
    assert any(m["source"] == "chat" for m in mems)


@pytest.mark.asyncio
async def test_turn_completes_after_client_disconnect(client):
    """Closing the browser mid-turn must not interrupt generation (async chat)."""

    import asyncio as _asyncio

    from app.schemas.chat import ChatRequest
    from app.services import chat_service

    gen = chat_service.stream_chat(ChatRequest(content="resilient hello"))
    first_raw = await gen.__anext__()  # 'start' event
    convo_id = json.loads(first_raw[len("data: ") :])["conversation_id"]

    # Simulate the client going away right after the stream starts.
    await gen.aclose()

    # The detached worker keeps running and persists the assistant reply.
    messages: list[dict] = []
    for _ in range(100):
        await _asyncio.sleep(0.02)
        resp = await client.get(f"/api/v1/conversations/{convo_id}")
        messages = resp.json()["messages"]
        if any(m["role"] == "assistant" and m["content"] for m in messages):
            break

    roles = [m["role"] for m in messages]
    assert "user" in roles and "assistant" in roles
