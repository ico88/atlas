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


async def _seed_gate(session, pid: str) -> str:
    """Stand in for an 'improvement' verdict: mark the proposal EXPERIMENTED and
    open the approval gate (in the hermetic echo env every model scores the same,
    so a natural improvement can't be produced)."""

    from app.models.approval import Approval, ApprovalStatus
    from app.models.improvement import ImprovementProposal, ProposalStatus

    proposal = await session.get(ImprovementProposal, pid)
    proposal.status = ProposalStatus.EXPERIMENTED.value
    gate = Approval(
        subject_type="improvement_proposal",
        subject_id=pid,
        action="apply_improvement",
        status=ApprovalStatus.PENDING.value,
    )
    session.add(gate)
    await session.commit()
    await session.refresh(gate)
    return gate.id


@pytest.mark.asyncio
async def test_neutral_experiment_opens_no_gate(client, session):
    """A neutral/regression result records the verdict but must NOT nag the human
    with an approval decision (Autopilot noise suppression)."""

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
    pid = created.json()["id"]
    assert created.json()["change"] == {"default_model": "cand-y"}

    exp = (await client.post(f"/api/v1/improvements/proposals/{pid}/experiment")).json()
    assert exp["status"] == "EXPERIMENTED"
    assert exp["recommendation"] == "neutral"  # echo -> identical -> no change
    # No approval gate for a non-improvement.
    approvals = (await client.get("/api/v1/approvals?status=PENDING")).json()
    assert not any(a["subject_id"] == pid for a in approvals["items"])
    # And it is not applied without a decision.
    assert (await client.post(f"/api/v1/improvements/proposals/{pid}/apply")).status_code == 409


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
    pid = proposal["id"]

    # Applying before approval is refused.
    early = await client.post(f"/api/v1/improvements/proposals/{pid}/apply")
    assert early.status_code == 409

    # An improvement opens the gate (seeded — see _seed_gate).
    gate_id = await _seed_gate(session, pid)

    # Approve -> proposal APPROVED.
    approved = await client.post(
        f"/api/v1/approvals/{gate_id}/approve", json={"decided_by": "alice"}
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
    gate_id = await _seed_gate(session, pid)
    await client.post(f"/api/v1/approvals/{gate_id}/reject", json={"decided_by": "bob"})
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
