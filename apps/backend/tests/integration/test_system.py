"""Integration tests for health / system status endpoints."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert "version" in body


@pytest.mark.asyncio
async def test_system_status_reports_components(client):
    resp = await client.get("/api/v1/system/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    names = {c["name"]: c["status"] for c in body["components"]}
    assert names["backend"] == "healthy"
    assert names["database"] == "healthy"
    assert names["redis"] == "healthy"


@pytest.mark.asyncio
async def test_request_id_echoed(client):
    resp = await client.get("/health", headers={"X-Request-ID": "corr-42"})
    assert resp.headers["X-Request-ID"] == "corr-42"


@pytest.mark.asyncio
async def test_metrics_endpoint(client):
    resp = await client.get("/api/v1/system/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert "tasks_by_status" in body
    assert body["approvals_pending"] == 0
