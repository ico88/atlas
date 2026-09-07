"""Service accounts — non-human API identities (ROADMAP R5)."""

from __future__ import annotations

import pytest
from app.services import service_account_service


@pytest.mark.asyncio
async def test_create_verify_revoke(session):
    account, token = await service_account_service.create(session, name="ci-bot", role="user")
    assert token.startswith("atlas_sa_")
    # Only the hash is stored, never the plaintext token.
    assert account.token_hash != token
    assert token not in account.token_hash

    verified = await service_account_service.verify(session, token)
    assert verified is not None and verified.name == "ci-bot"
    assert verified.last_used_at is not None

    # A wrong token does not verify.
    assert await service_account_service.verify(session, "atlas_sa_wrong") is None

    assert await service_account_service.revoke(session, account.id) is True
    assert await service_account_service.verify(session, token) is None  # revoked


@pytest.mark.asyncio
async def test_service_account_api_flow(client):
    created = await client.post(
        "/api/v1/service-accounts", json={"name": "deploy-bot", "role": "admin"}
    )
    assert created.status_code == 201
    body = created.json()
    token = body["token"]
    assert token.startswith("atlas_sa_")

    # Listing never returns the plaintext token.
    lst = await client.get("/api/v1/service-accounts")
    assert lst.status_code == 200
    assert all("token" not in a for a in lst.json())

    # The token authenticates via the X-Service-Token header.
    who = await client.get(
        "/api/v1/service-accounts/whoami", headers={"X-Service-Token": token}
    )
    assert who.status_code == 200 and who.json()["name"] == "deploy-bot"

    # After revoke the token stops working.
    rev = await client.post(f"/api/v1/service-accounts/{body['id']}/revoke")
    assert rev.status_code == 200
    who2 = await client.get(
        "/api/v1/service-accounts/whoami", headers={"X-Service-Token": token}
    )
    assert who2.status_code == 401
