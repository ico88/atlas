"""Semi-automatic advancement of maintenance & improvement loops."""

from __future__ import annotations

import pytest
from app.models.improvement import ProposalStatus
from app.models.maintenance import IssueStatus, RunStatus
from app.services import (
    automation_service,
    eval_service,
    improvement_service,
    maintenance_service,
)

LOG = {
    "message": "auto_advance boom in service",
    "service": "backend",
    "level": "ERROR",
    "event": "auto_boom",
}


@pytest.mark.asyncio
async def test_advance_issue_prepares_fix_awaiting_approval(session):
    issue = await maintenance_service.ingest_log(session, **LOG)
    assert issue.status == IssueStatus.OPEN.value

    did = await automation_service.advance_issue(session, issue.id)
    assert did is True

    # Reload from a clean identity map (a background worker uses a fresh session).
    session.expunge_all()
    issue = await maintenance_service.get_issue(session, issue.id)
    assert issue.status == IssueStatus.FIX_PROPOSED.value
    assert issue.runs[-1].status == RunStatus.NEEDS_APPROVAL.value
    # The sandbox actually ran during the auto-prepared fix.
    assert "applies cleanly" in (issue.runs[-1].tests_summary or "")


@pytest.mark.asyncio
async def test_advance_issue_is_idempotent(session):
    issue = await maintenance_service.ingest_log(session, **LOG)
    assert await automation_service.advance_issue(session, issue.id) is True
    # A second pass must not stack another fix / approval gate.
    assert await automation_service.advance_issue(session, issue.id) is False


@pytest.mark.asyncio
async def test_advance_proposal_runs_experiment(session):
    suite = await eval_service.create_suite(session, name="auto-suite")
    await eval_service.add_case(
        session, suite_id=suite.id, input="hi", expected_substrings=["hi"]
    )
    proposal = await improvement_service.create_proposal(
        session, title="auto", suite_id=suite.id, candidate_model="c"
    )
    assert proposal.status == ProposalStatus.DRAFT.value

    did = await automation_service.advance_proposal(session, proposal.id)
    assert did is True

    proposal = await improvement_service.get_proposal(session, proposal.id)
    assert proposal.status == ProposalStatus.EXPERIMENTED.value
    assert proposal.recommendation in {"improvement", "regression", "neutral", "inconclusive"}


@pytest.mark.asyncio
async def test_advance_proposal_needs_suite(session):
    proposal = await improvement_service.create_proposal(
        session, title="no-suite", candidate_model="c"
    )
    assert await automation_service.advance_proposal(session, proposal.id) is False


@pytest.mark.asyncio
async def test_autonomous_proposer_generates_and_dedups(session):
    from app.models.provider import LLMModel

    suite = await eval_service.create_suite(session, name="auto-propose-suite")
    await eval_service.add_case(
        session, suite_id=suite.id, input="x", expected_substrings=["x"]
    )
    # Two available models; no default set -> both are candidates.
    session.add(LLMModel(provider="ollama", name="model-a", available=True))
    session.add(LLMModel(provider="ollama", name="model-b", available=True))
    await session.commit()

    created = await improvement_service.propose_model_candidates(session)
    assert {p.candidate_model for p in created} == {"model-a", "model-b"}
    assert all(p.category == "model" and p.suite_id == suite.id for p in created)

    # A second sweep must not duplicate proposals for the same candidates.
    again = await improvement_service.propose_model_candidates(session)
    assert again == []


@pytest.mark.asyncio
async def test_autonomous_proposer_noop_without_suite(session):
    from app.models.provider import LLMModel

    session.add(LLMModel(provider="ollama", name="solo", available=True))
    await session.commit()
    assert await improvement_service.propose_model_candidates(session) == []
