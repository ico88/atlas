"""Integration tests for the Node federation API."""

from __future__ import annotations

import pytest

REGISTER = {
    "node_id": "node-a",
    "hostname": "worker-1",
    "label": "GPU worker",
    "version": "0.1.0",
    "capabilities": {"llm": True, "build": True},
    "hardware": {"cpu_cores": 8, "ram_mb": 16000},
}


@pytest.mark.asyncio
async def test_register_then_appears_online(client):
    resp = await client.post("/api/v1/nodes/register", json=REGISTER)
    assert resp.status_code == 201
    body = resp.json()
    assert body["node_id"] == "node-a"
    assert body["status"] == "online"
    assert body["online"] is True
    assert body["capabilities"]["llm"] is True

    listing = await client.get("/api/v1/nodes")
    assert listing.status_code == 200
    data = listing.json()
    assert data["total"] == 1
    assert data["online"] == 1


@pytest.mark.asyncio
async def test_register_is_idempotent(client):
    await client.post("/api/v1/nodes/register", json=REGISTER)
    await client.post("/api/v1/nodes/register", json={**REGISTER, "label": "renamed"})

    listing = (await client.get("/api/v1/nodes")).json()
    assert listing["total"] == 1
    assert listing["items"][0]["label"] == "renamed"


@pytest.mark.asyncio
async def test_heartbeat_updates_node(client):
    await client.post("/api/v1/nodes/register", json=REGISTER)
    resp = await client.post(
        "/api/v1/nodes/node-a/heartbeat",
        json={"status": "online", "health": {"load": 0.3, "ram_free_mb": 8000}},
    )
    assert resp.status_code == 200
    assert resp.json()["hardware"]["health"]["load"] == 0.3


@pytest.mark.asyncio
async def test_get_node_by_ref_and_404(client):
    created = (await client.post("/api/v1/nodes/register", json=REGISTER)).json()
    by_node_id = await client.get("/api/v1/nodes/node-a")
    by_db_id = await client.get(f"/api/v1/nodes/{created['id']}")
    assert by_node_id.status_code == 200
    assert by_db_id.status_code == 200

    missing = await client.get("/api/v1/nodes/nope")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_metrics_counts_nodes(client):
    await client.post("/api/v1/nodes/register", json=REGISTER)
    metrics = (await client.get("/api/v1/system/metrics")).json()
    assert metrics["nodes_total"] == 1
    assert metrics["nodes_online"] == 1


@pytest.mark.asyncio
async def test_token_enforced_when_configured(client, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "node_join_token", "secret-token")

    denied = await client.post("/api/v1/nodes/register", json=REGISTER)
    assert denied.status_code == 401

    allowed = await client.post(
        "/api/v1/nodes/register",
        json=REGISTER,
        headers={"X-Node-Token": "secret-token"},
    )
    assert allowed.status_code == 201
