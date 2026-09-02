"""Integration tests for the model registry and hardware scan (M2)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_models_refresh_discovers_echo(client):
    # No Ollama in tests, so the echo provider's model should be registered.
    refreshed = await client.post("/api/v1/models/refresh")
    assert refreshed.status_code == 200
    names = {m["name"] for m in refreshed.json()["items"]}
    assert "echo-local" in names

    listing = await client.get("/api/v1/models")
    assert listing.status_code == 200
    assert listing.json()["total"] >= 1


@pytest.mark.asyncio
async def test_models_refresh_is_idempotent(client):
    first = (await client.post("/api/v1/models/refresh")).json()["total"]
    second = (await client.post("/api/v1/models/refresh")).json()["total"]
    assert first == second


@pytest.mark.asyncio
async def test_hardware_scan(client):
    resp = await client.get("/api/v1/system/hardware")
    assert resp.status_code == 200
    body = resp.json()
    assert "cpu_cores" in body
    assert "platform" in body
    assert "ram_total_mb" in body
