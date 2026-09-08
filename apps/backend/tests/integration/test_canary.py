"""Canary rollout: health gate + auto-rollback (ROADMAP R6)."""

from __future__ import annotations

import pytest
from app.models.eval import EvalRun, EvalRunStatus, EvalSuite
from app.models.improvement import ImprovementProposal, ProposalStatus
from app.services import canary_service, settings_service


# --------------------------------------------------------------------------- #
# Pure health gate
# --------------------------------------------------------------------------- #
def test_decide_promote_when_healthy_and_no_regression():
    d, _ = canary_service.decide(
        baseline_quality=0.8, candidate_quality=0.82, healthy=True, tolerance=0.05
    )
    assert d == "promote"


def test_decide_rollback_on_quality_regression():
    d, reason = canary_service.decide(
        baseline_quality=0.9, candidate_quality=0.5, healthy=True, tolerance=0.05
    )
    assert d == "rollback" and "regress" in reason


def test_decide_rollback_when_unhealthy():
    d, _ = canary_service.decide(
        baseline_quality=0.5, candidate_quality=0.9, healthy=False, tolerance=0.05
    )
    assert d == "rollback"


def test_decide_promote_without_quality_data():
    d, _ = canary_service.decide(
        baseline_quality=None, candidate_quality=None, healthy=True, tolerance=0.05
    )
    assert d == "promote"


# --------------------------------------------------------------------------- #
# Canary flow
# --------------------------------------------------------------------------- #
async def _approved_proposal(session, candidate="cand-model") -> ImprovementProposal:
    p = ImprovementProposal(
        title="try candidate",
        category="model",
        candidate_model=candidate,
        change={"default_model": candidate},
        status=ProposalStatus.APPROVED.value,
    )
    session.add(p)
    await session.commit()
    await session.refresh(p)
    return p


async def _eval(session, model, avg_quality):
    suite = EvalSuite(name=f"s-{model}")
    session.add(suite)
    await session.flush()
    session.add(
        EvalRun(
            suite_id=suite.id, model=model, status=EvalRunStatus.COMPLETED.value,
            metrics={"avg_quality": avg_quality},
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_start_applies_candidate_and_records_rollback_point(session):
    await settings_service.set_ai_config({"default_model": "old-model"}, session)
    p = await _approved_proposal(session, "new-model")

    p = await canary_service.start(session, p)
    assert p.status == ProposalStatus.CANARY.value
    canary = p.comparison["canary"]
    assert canary["previous_default_model"] == "old-model"
    # Candidate is live during the canary.
    cfg = await settings_service.get_ai_config_public()
    assert cfg["default_model"] == "new-model"


@pytest.mark.asyncio
async def test_evaluate_promotes_when_candidate_better(session):
    await settings_service.set_ai_config({"default_model": "old-model"}, session)
    await _eval(session, "old-model", 0.6)
    await _eval(session, "new-model", 0.9)
    p = await _approved_proposal(session, "new-model")
    p = await canary_service.start(session, p)

    p = await canary_service.evaluate(session, p)
    assert p.status == ProposalStatus.APPLIED.value
    cfg = await settings_service.get_ai_config_public()
    assert cfg["default_model"] == "new-model"  # promoted, stays live


@pytest.mark.asyncio
async def test_evaluate_rolls_back_when_candidate_worse(session):
    await settings_service.set_ai_config({"default_model": "old-model"}, session)
    await _eval(session, "old-model", 0.9)
    await _eval(session, "new-model", 0.4)
    p = await _approved_proposal(session, "new-model")
    p = await canary_service.start(session, p)

    p = await canary_service.evaluate(session, p)
    assert p.status == ProposalStatus.ROLLED_BACK.value
    cfg = await settings_service.get_ai_config_public()
    assert cfg["default_model"] == "old-model"  # auto-reverted
    assert "regress" in p.comparison["canary"]["reason"]


@pytest.mark.asyncio
async def test_start_requires_approved(session):
    p = ImprovementProposal(
        title="x", category="model", change={"default_model": "m"},
        status=ProposalStatus.DRAFT.value,
    )
    session.add(p)
    await session.commit()
    with pytest.raises(canary_service.CanaryError):
        await canary_service.start(session, p)
