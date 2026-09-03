"""Node enrollment tests (ROADMAP PR 6): invite, approve, revoke, rotate, gate."""

from __future__ import annotations

import pytest
from app.core.config import get_settings
from app.models.node_enrollment import EnrollmentStatus
from app.services import enrollment_service


@pytest.fixture
def _enrollment_required():
    """Turn on enrollment enforcement for the duration of a test."""
    settings = get_settings()
    original = settings.node_enrollment_required
    settings.node_enrollment_required = True
    yield
    settings.node_enrollment_required = original


# --------------------------------------------------------------------------- #
# service-level
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_create_returns_token_and_hashes_at_rest(session):
    enrollment, token = await enrollment_service.create_enrollment(
        session, node_id="node-a", label="gpu"
    )
    assert enrollment.status == EnrollmentStatus.PENDING.value
    assert token  # plaintext returned once
    assert enrollment.token_hash == enrollment_service.hash_token(token)
    assert token not in enrollment.token_hash  # never stored in the clear
    assert enrollment.token_prefix == token[:8]


@pytest.mark.asyncio
async def test_authenticate_resolves_and_rotate_invalidates(session):
    enrollment, token = await enrollment_service.create_enrollment(session, node_id="node-b")
    found = await enrollment_service.authenticate(session, token)
    assert found is not None and found.id == enrollment.id

    _rotated, new_token = await enrollment_service.rotate(session, enrollment)
    assert new_token != token
    # Old token no longer resolves; the new one does.
    assert await enrollment_service.authenticate(session, token) is None
    assert (await enrollment_service.authenticate(session, new_token)).id == enrollment.id


@pytest.mark.asyncio
async def test_duplicate_node_id_rejected(session):
    await enrollment_service.create_enrollment(session, node_id="dup")
    with pytest.raises(ValueError):
        await enrollment_service.create_enrollment(session, node_id="dup")


# --------------------------------------------------------------------------- #
# API + gate
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_disabled_by_default_register_open(client):
    # With enrollment not required, registration works without any enrollment.
    resp = await client.post("/api/v1/nodes/register", json={"node_id": "free-node"})
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_full_lifecycle_gates_claim(client, _enrollment_required):
    # 1) Operator invites the node.
    created = await client.post(
        "/api/v1/enrollments", json={"node_id": "worker-1", "label": "gpu"}
    )
    assert created.status_code == 201
    token = created.json()["token"]
    enrollment_id = created.json()["id"]
    assert created.json()["status"] == "PENDING"

    headers = {"X-Node-Token": token}

    # 2) Node registers with its token while PENDING (allowed).
    reg = await client.post(
        "/api/v1/nodes/register",
        json={"node_id": "worker-1", "capabilities": {"build": True}},
        headers=headers,
    )
    assert reg.status_code == 201

    # A wrong token is rejected.
    bad = await client.post(
        "/api/v1/nodes/register", json={"node_id": "worker-1"}, headers={"X-Node-Token": "nope"}
    )
    assert bad.status_code == 401

    # 3) Claiming is blocked until approved.
    claim = await client.post("/api/v1/nodes/worker-1/claim-task", headers=headers)
    assert claim.status_code == 403

    # 4) Approve, then claim is allowed (returns null: no tasks queued).
    approve = await client.post(f"/api/v1/enrollments/{enrollment_id}/approve")
    assert approve.status_code == 200 and approve.json()["status"] == "APPROVED"
    claim2 = await client.post("/api/v1/nodes/worker-1/claim-task", headers=headers)
    assert claim2.status_code == 200

    # 5) Revoke, then even heartbeat/claim are blocked.
    revoke = await client.post(f"/api/v1/enrollments/{enrollment_id}/revoke")
    assert revoke.status_code == 200 and revoke.json()["status"] == "REVOKED"
    hb = await client.post(
        "/api/v1/nodes/worker-1/heartbeat", json={"status": "online"}, headers=headers
    )
    assert hb.status_code == 403


@pytest.mark.asyncio
async def test_register_requires_token_when_enabled(client, _enrollment_required):
    resp = await client.post("/api/v1/nodes/register", json={"node_id": "no-token"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_enrollments(client):
    await client.post("/api/v1/enrollments", json={"node_id": "listed-node"})
    listing = await client.get("/api/v1/enrollments")
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] >= 1
    # The list view never exposes the secret token, only its prefix.
    first = body["items"][0]
    assert "token" not in first
    assert "token_prefix" in first
