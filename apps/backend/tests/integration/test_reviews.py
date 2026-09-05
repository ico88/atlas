"""Integration tests for the critical-review pipeline (ROADMAP PR 19)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_run_review_persists_rounds_and_decision(client):
    resp = await client.post(
        "/api/v1/reviews",
        json={"prompt": "Name the capital of Italy.", "references": ["Name the capital"]},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["round_count"] >= 1
    assert body["rounds"] and "findings" in body["rounds"][0]
    assert body["consensus"]["best_index"] >= 0
    assert body["decision"] in {"accept", "revise", "reject"}
    # The echo answer contains the prompt, so the reference is grounded.
    assert body["best_answer"]


@pytest.mark.asyncio
async def test_review_listing_and_detail(client):
    created = (
        await client.post("/api/v1/reviews", json={"prompt": "Explain gravity briefly."})
    ).json()
    listing = (await client.get("/api/v1/reviews")).json()
    assert listing["total"] >= 1
    detail = await client.get(f"/api/v1/reviews/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == created["id"]


@pytest.mark.asyncio
async def test_review_adaptive_stops_or_caps_rounds(client):
    # Cap rounds at 2; never exceed it.
    body = (
        await client.post(
            "/api/v1/reviews", json={"prompt": "hello", "max_rounds": 2}
        )
    ).json()
    assert 1 <= body["round_count"] <= 2
