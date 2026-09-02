"""Integration tests for the Task API."""

from __future__ import annotations

import pytest
from app.services import queue


@pytest.mark.asyncio
async def test_create_task_returns_queued_and_enqueues(client):
    resp = await client.post("/api/v1/tasks", json={"title": "demo", "payload": {"x": 1}})
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "QUEUED"
    assert body["title"] == "demo"
    assert body["correlation_id"]

    # The task id was pushed onto the work queue.
    assert await queue.queue_depth() == 1


@pytest.mark.asyncio
async def test_get_and_list_task(client):
    created = (await client.post("/api/v1/tasks", json={"title": "t1"})).json()
    task_id = created["id"]

    got = await client.get(f"/api/v1/tasks/{task_id}")
    assert got.status_code == 200
    assert got.json()["id"] == task_id

    listing = await client.get("/api/v1/tasks")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1


@pytest.mark.asyncio
async def test_get_missing_task_404(client):
    resp = await client.get("/api/v1/tasks/does-not-exist")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cancel_task(client):
    created = (await client.post("/api/v1/tasks", json={"title": "cancel-me"})).json()
    task_id = created["id"]

    resp = await client.post(f"/api/v1/tasks/{task_id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_task_events_recorded(client):
    created = (await client.post("/api/v1/tasks", json={"title": "with-events"})).json()
    task_id = created["id"]

    resp = await client.get(f"/api/v1/tasks/{task_id}/events")
    assert resp.status_code == 200
    events = resp.json()
    assert any(e["event_type"] == "created" for e in events)
    assert events[0]["status"] == "QUEUED"
