"""Integration tests for authentication (spec §15)."""

from __future__ import annotations

import pytest
from app.services import user_service


async def _make_user(session, email="user@atlas.ai", password="s3cret-pass"):
    return await user_service.create_user(session, email=email, password=password)


@pytest.mark.asyncio
async def test_login_returns_token_and_me_works(client, session):
    await _make_user(session)

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@atlas.ai", "password": "s3cret-pass"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert login.json()["token_type"] == "bearer"

    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == "user@atlas.ai"


@pytest.mark.asyncio
async def test_login_wrong_password(client, session):
    await _make_user(session)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@atlas.ai", "password": "wrong"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_user(client):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@atlas.ai", "password": "whatever"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_auth(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code in (401, 403)  # missing bearer credentials


@pytest.mark.asyncio
async def test_me_rejects_bad_token(client):
    resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_inactive_user_cannot_login(client, session):
    user = await _make_user(session, email="off@atlas.ai")
    user.is_active = False
    await session.commit()

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "off@atlas.ai", "password": "s3cret-pass"},
    )
    assert resp.status_code == 401
