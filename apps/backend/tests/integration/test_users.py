"""User management + RBAC tests (ROADMAP PR 27)."""

from __future__ import annotations

import pytest
from app.core.security import create_access_token


@pytest.mark.asyncio
async def test_open_mode_allows_user_management(client):
    # Open mode (default): no token needed.
    empty = await client.get("/api/v1/users")
    assert empty.status_code == 200
    assert empty.json()["auth_enforced"] is False

    admin = await client.post(
        "/api/v1/users",
        json={"email": "boss@example.com", "password": "secret123", "role": "admin"},
    )
    assert admin.status_code == 201
    assert admin.json()["role"] == "admin"

    member = await client.post(
        "/api/v1/users",
        json={"email": "member@example.com", "password": "secret123", "role": "user"},
    )
    assert member.status_code == 201
    member_id = member.json()["id"]

    listing = (await client.get("/api/v1/users")).json()
    assert listing["total"] == 2

    # Promote the member to admin.
    promoted = await client.patch(f"/api/v1/users/{member_id}", json={"role": "admin"})
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_duplicate_email_conflicts(client):
    body = {"email": "dup@example.com", "password": "secret123"}
    assert (await client.post("/api/v1/users", json=body)).status_code == 201
    assert (await client.post("/api/v1/users", json=body)).status_code == 409


@pytest.mark.asyncio
async def test_cannot_remove_last_admin(client):
    admin = (
        await client.post(
            "/api/v1/users",
            json={"email": "solo@example.com", "password": "secret123", "role": "admin"},
        )
    ).json()
    # Demoting the only admin is refused.
    demote = await client.patch(f"/api/v1/users/{admin['id']}", json={"role": "user"})
    assert demote.status_code == 409
    # Deactivating the only admin is refused too.
    off = await client.patch(f"/api/v1/users/{admin['id']}", json={"is_active": False})
    assert off.status_code == 409


@pytest.mark.asyncio
async def test_enforced_mode_requires_admin(client, session, monkeypatch):
    from app.api import deps
    from app.services import user_service

    # Seed an admin and a plain user in open mode.
    admin = await user_service.create_user(
        session, email="a@example.com", password="secret123", role="admin"
    )
    member = await user_service.create_user(
        session, email="u@example.com", password="secret123", role="user"
    )

    # Turn enforcement on for the deps layer.
    real = deps.get_settings()

    class _S:
        auth_enforce = True

        def __getattr__(self, k):  # fall through for anything else
            return getattr(real, k)

    monkeypatch.setattr(deps, "get_settings", lambda: _S())

    # No token -> 401.
    assert (await client.get("/api/v1/users")).status_code == 401

    # Non-admin token -> 403.
    utok = create_access_token(subject=member.id, role="user")
    r = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {utok}"})
    assert r.status_code == 403

    # Admin token -> 200.
    atok = create_access_token(subject=admin.id, role="admin")
    r = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {atok}"})
    assert r.status_code == 200
