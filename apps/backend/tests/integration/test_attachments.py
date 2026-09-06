"""Chat file upload: extraction, upload API, and use as chat context."""

from __future__ import annotations

import base64
import json

import pytest
from app.models.attachment import Attachment
from app.services import attachment_service
from sqlalchemy import select


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


# --------------------------------------------------------------------------- #
# Extraction (pure)
# --------------------------------------------------------------------------- #
def test_extract_text_plain():
    text, err = attachment_service.extract_text("notes.txt", "text/plain", b"ciao mondo")
    assert err is None and text == "ciao mondo"


def test_extract_code_and_json():
    text, err = attachment_service.extract_text("a.py", None, b"def f():\n    return 1\n")
    assert err is None and "def f()" in text
    text, err = attachment_service.extract_text("d.json", None, b'{"x": 1}')
    assert err is None and '"x"' in text


def test_extract_rejects_binary():
    _, err = attachment_service.extract_text("a.bin", None, b"\x00\x01\x02\x00binary")
    assert err is not None


def test_extract_rejects_too_large():
    big = b"x" * (attachment_service.MAX_BYTES + 1)
    _, err = attachment_service.extract_text("big.txt", "text/plain", big)
    assert err is not None and "grande" in err


def test_build_context_is_bounded():
    atts = [Attachment(filename="f.txt", text_content="A" * 50_000)]
    block = attachment_service.build_context(atts)
    assert "FILE: f.txt" in block
    assert len(block) <= attachment_service.MAX_CONTEXT_CHARS + 200


# --------------------------------------------------------------------------- #
# Upload API
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_upload_attachment_api(client):
    r = await client.post(
        "/api/v1/chat/attachments",
        json={"filename": "report.md", "content_type": "text/markdown",
              "data_b64": _b64(b"# Titolo\nContenuto importante.")},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["filename"] == "report.md"
    assert body["chars"] > 0
    assert "Titolo" in body["preview"]


@pytest.mark.asyncio
async def test_upload_rejects_unsupported(client):
    r = await client.post(
        "/api/v1/chat/attachments",
        json={"filename": "x.bin", "data_b64": _b64(b"\x00\x00\x00\x00binary blob")},
    )
    assert r.status_code == 415


@pytest.mark.asyncio
async def test_upload_rejects_bad_base64(client):
    r = await client.post(
        "/api/v1/chat/attachments",
        json={"filename": "x.txt", "data_b64": "not!base64!"},
    )
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Attachment used as chat context (end to end)
# --------------------------------------------------------------------------- #
def _parse_sse(text: str) -> list[dict]:
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


@pytest.mark.asyncio
async def test_chat_uses_attachment_context(client, session):
    up = await client.post(
        "/api/v1/chat/attachments",
        json={"filename": "secret.txt", "content_type": "text/plain",
              "data_b64": _b64(b"la parola magica e' BALENA")},
    )
    att_id = up.json()["id"]

    async with client.stream(
        "POST", "/api/v1/chat/stream",
        json={"content": "qual e' la parola magica?", "attachment_ids": [att_id]},
    ) as resp:
        assert resp.status_code == 200
        body = ""
        async for chunk in resp.aiter_text():
            body += chunk

    events = _parse_sse(body)
    # The echo provider echoes the last user message; the important assertion is
    # that the turn completed and the attachment is now linked to the message.
    assert events[-1]["type"] == "done"
    att = (
        await session.execute(select(Attachment).where(Attachment.id == att_id))
    ).scalar_one()
    assert att.message_id is not None  # linked to the user message
    assert att.conversation_id is not None
