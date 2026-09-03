"""Integration tests for Continuous Improvement (ROADMAP PR 18)."""

from __future__ import annotations

import pytest
from app.services import eval_service


async def _seed_suite(session) -> str:
    suite = await eval_service.create_suite(session, name="improve-smoke")
    # Echo provider echoes the input, so expecting the input yields quality 1.0.
    await eval_service.add_case(
        session, suite_id=suite.id, input="hello", expected_substrings=["hello"]
    )
    return suite.id


@pytest.mark.asyncio
async def test_full_improvement_flow_with_approval_gate(client, session):
    suite_id = await _seed_suite(session)

    created = await client.post(
        "/api/v1/improvements/proposals",
        json={
            "title": "Try candidate model",
            "category": "model",
            "suite_id": suite_id,
            "baseline_model": "base-x",
            "candidate_model": "cand-y",
        },
    )
    assert created.status_code == 201
    proposal = created.json()
    assert proposal["status"] == "DRAFT"
    # A model proposal implies the change to apply.
    assert proposal["change"] == {"default_model": "cand-y"}

    pid = proposal["id"]

    # Applying before experiment/approval is refused.
    early = await client.post(f"/api/v1/improvements/proposals/{pid}/apply")
    assert early.status_code == 409

    # Run the experiment: baseline vs candidate on the suite.
    experimented = await client.post(f"/api/v1/improvements/proposals/{pid}/experiment")
    assert experimented.status_code == 200
    exp = experimented.json()
    assert exp["status"] == "EXPERIMENTED"
    assert exp["baseline_run_id"] and exp["candidate_run_id"]
    # Echo is identical for both models -> no meaningful change.
    assert exp["recommendation"] == "neutral"
    assert "deltas" in exp["comparison"]

    # A pending approval gate was opened.
    approvals = (await client.get("/api/v1/approvals?status=PENDING")).json()
    gate = next(a for a in approvals["items"] if a["subject_id"] == pid)
    assert gate["subject_type"] == "improvement_proposal"

    # Still cannot apply until approved.
    still = await client.post(f"/api/v1/improvements/proposals/{pid}/apply")
    assert still.status_code == 409

    # Approve -> proposal APPROVED.
    approved = await client.post(
        f"/api/v1/approvals/{gate['id']}/approve", json={"decided_by": "alice"}
    )
    assert approved.status_code == 200
    detail = (await client.get(f"/api/v1/improvements/proposals/{pid}")).json()
    assert detail["status"] == "APPROVED"

    # Apply -> the default model is set and the proposal is APPLIED.
    applied = await client.post(f"/api/v1/improvements/proposals/{pid}/apply")
    assert applied.status_code == 200
    assert applied.json()["status"] == "APPLIED"

    ai = (await client.get("/api/v1/models/default")).json()
    assert ai["default_model"] == "cand-y"


@pytest.mark.asyncio
async def test_reject_marks_proposal_rejected(client, session):
    suite_id = await _seed_suite(session)
    pid = (
        await client.post(
            "/api/v1/improvements/proposals",
            json={"title": "p", "suite_id": suite_id, "candidate_model": "c"},
        )
    ).json()["id"]
    await client.post(f"/api/v1/improvements/proposals/{pid}/experiment")
    gate = next(
        a
        for a in (await client.get("/api/v1/approvals?status=PENDING")).json()["items"]
        if a["subject_id"] == pid
    )
    await client.post(f"/api/v1/approvals/{gate['id']}/reject", json={"decided_by": "bob"})
    detail = (await client.get(f"/api/v1/improvements/proposals/{pid}")).json()
    assert detail["status"] == "REJECTED"


@pytest.mark.asyncio
async def test_experiment_requires_suite(client):
    pid = (
        await client.post(
            "/api/v1/improvements/proposals",
            json={"title": "no suite", "candidate_model": "c"},
        )
    ).json()["id"]
    resp = await client.post(f"/api/v1/improvements/proposals/{pid}/experiment")
    assert resp.status_code == 409
