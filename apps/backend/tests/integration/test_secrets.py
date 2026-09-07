"""Secret manager — encrypted at rest (ROADMAP R5)."""

from __future__ import annotations

import pytest
from app.models.secret import Secret
from app.services import secret_service
from sqlalchemy import select


def test_encrypt_roundtrip_and_not_plaintext():
    ct = secret_service.encrypt("hunter2")
    assert ct != "hunter2"
    assert secret_service.decrypt(ct) == "hunter2"


@pytest.mark.asyncio
async def test_set_get_stored_encrypted(session):
    await secret_service.set_secret(session, name="OPENAI_KEY", value="sk-secret")
    # Stored ciphertext must not contain the plaintext.
    row = (
        await session.execute(select(Secret).where(Secret.name == "OPENAI_KEY"))
    ).scalar_one()
    assert "sk-secret" not in row.ciphertext
    assert await secret_service.get_secret(session, "OPENAI_KEY") == "sk-secret"


@pytest.mark.asyncio
async def test_delete(session):
    await secret_service.set_secret(session, name="X", value="v")
    assert await secret_service.delete_secret(session, "X") is True
    assert await secret_service.get_secret(session, "X") is None


@pytest.mark.asyncio
async def test_secrets_api_never_lists_plaintext(client):
    up = await client.put(
        "/api/v1/secrets", json={"name": "TOKEN", "value": "top-secret", "description": "n"}
    )
    assert up.status_code == 200

    lst = await client.get("/api/v1/secrets")
    assert lst.status_code == 200
    body = lst.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "TOKEN"
    assert "value" not in body["items"][0]  # no plaintext in the listing

    # Reveal is a separate, explicit action.
    rv = await client.get("/api/v1/secrets/TOKEN/reveal")
    assert rv.status_code == 200 and rv.json()["value"] == "top-secret"

    dele = await client.delete("/api/v1/secrets/TOKEN")
    assert dele.status_code == 200
    assert (await client.get("/api/v1/secrets")).json()["total"] == 0
