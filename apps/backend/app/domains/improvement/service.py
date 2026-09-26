"""Continuous Improvement service (ROADMAP PR 18).

Propose a change, run an experiment (baseline vs candidate on an eval suite),
compare the metrics, and — only after a human approves — apply it. Safety is the
overriding signal: a candidate that lowers safety is a regression no matter what
else improves. Comparison is a pure function so it is unit-testable offline.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import Approval, ApprovalStatus
from app.models.improvement import (
    ImprovementProposal,
    ProposalCategory,
    ProposalStatus,
)
from app.services import eval_service, settings_service

logger = logging.getLogger(__name__)

# Deltas smaller than this are treated as noise (identical within rounding).
_EPS = 1e-4


class ImprovementStateError(RuntimeError):
    """Raised when a proposal action is requested in a state that forbids it."""


# --------------------------------------------------------------------------- #
# pure comparison
# --------------------------------------------------------------------------- #
def compare_metrics(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Compare two aggregate metric dicts and return {deltas, verdict}.

    verdict:
      * ``regression``    — safety dropped, or quality/pass_rate dropped with no gain
      * ``improvement``   — quality/pass_rate gained with no safety/quality drop
      * ``neutral``       — no meaningful change
      * ``inconclusive``  — not enough data to compare
    """

    keys = ["pass_rate", "avg_quality", "avg_safety", "avg_latency_ms", "p95_latency_ms"]
    deltas: dict[str, float | None] = {}
    for k in keys:
        b = baseline.get(k)
        c = candidate.get(k)
        if isinstance(b, int | float) and isinstance(c, int | float):
            deltas[k] = round(c - b, 4)
        else:
            deltas[k] = None

    safety = deltas.get("avg_safety")
    quality = deltas.get("avg_quality")
    passd = deltas.get("pass_rate")

    if quality is None and passd is None and safety is None:
        verdict = "inconclusive"
    elif safety is not None and safety < -_EPS:
        # Never accept a safety regression, whatever else improves.
        verdict = "regression"
    else:
        gained = (quality is not None and quality > _EPS) or (
            passd is not None and passd > _EPS
        )
        lost = (quality is not None and quality < -_EPS) or (
            passd is not None and passd < -_EPS
        )
        if gained and not lost:
            verdict = "improvement"
        elif lost and not gained:
            verdict = "regression"
        else:
            verdict = "neutral"

    return {"deltas": deltas, "verdict": verdict}


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #
async def create_proposal(
    session: AsyncSession,
    *,
    title: str,
    description: str | None = None,
    category: str = ProposalCategory.MODEL.value,
    suite_id: str | None = None,
    baseline_model: str | None = None,
    candidate_model: str | None = None,
    change: dict[str, Any] | None = None,
) -> ImprovementProposal:
    # For a model proposal, the change to apply is implied by the candidate model.
    if change is None and category == ProposalCategory.MODEL.value and candidate_model:
        change = {"default_model": candidate_model}
    proposal = ImprovementProposal(
        title=title,
        description=description,
        category=category,
        suite_id=suite_id,
        baseline_model=baseline_model,
        candidate_model=candidate_model,
        change=change,
        status=ProposalStatus.DRAFT.value,
    )
    session.add(proposal)
    await session.commit()
    await session.refresh(proposal)
    # Semi-auto: run the baseline-vs-candidate experiment in the background so the
    # proposal reaches a verdict + approval gate by itself.
    from app.services import automation_service

    automation_service.maybe_advance_proposal(proposal.id)
    return proposal


async def list_proposals(
    session: AsyncSession, *, status: str | None = None
) -> list[ImprovementProposal]:
    query = select(ImprovementProposal).order_by(ImprovementProposal.created_at.desc())
    if status:
        query = query.where(ImprovementProposal.status == status)
    return list((await session.execute(query)).scalars().all())


async def get_proposal(session: AsyncSession, proposal_id: str) -> ImprovementProposal | None:
    return await session.get(ImprovementProposal, proposal_id)


# --------------------------------------------------------------------------- #
# experiment + apply
# --------------------------------------------------------------------------- #
async def run_experiment(
    session: AsyncSession, proposal: ImprovementProposal
) -> tuple[ImprovementProposal, Approval | None]:
    """Evaluate baseline vs candidate on the suite and compare.

    An approval gate is opened **only when the candidate is a measured
    improvement** — a neutral, inconclusive or regression result records the
    verdict but does not nag the human with a decision. This is what keeps the
    Autopilot decisions meaningful instead of one request per available model.
    """

    if not proposal.suite_id:
        raise ImprovementStateError("Proposal has no eval suite to experiment on")

    baseline = await eval_service.run_suite(
        session, proposal.suite_id, model=proposal.baseline_model, is_baseline=True
    )
    candidate = await eval_service.run_suite(
        session, proposal.suite_id, model=proposal.candidate_model
    )
    comparison = compare_metrics(baseline.metrics or {}, candidate.metrics or {})

    proposal.baseline_run_id = baseline.id
    proposal.candidate_run_id = candidate.id
    proposal.comparison = comparison
    proposal.recommendation = comparison["verdict"]
    proposal.status = ProposalStatus.EXPERIMENTED.value

    approval: Approval | None = None
    if comparison["verdict"] == "improvement":
        approval = Approval(
            subject_type="improvement_proposal",
            subject_id=proposal.id,
            action="apply_improvement",
            status=ApprovalStatus.PENDING.value,
            requested_by="improvement-agent",
            reason=(
                f"Experiment for '{proposal.title}': improvement "
                f"(candidate {proposal.candidate_model or 'default'} vs baseline "
                f"{proposal.baseline_model or 'default'})"
            ),
        )
        session.add(approval)
    await session.commit()
    await session.refresh(proposal)
    if approval is not None:
        await session.refresh(approval)
    logger.info(
        "improvement experiment done",
        extra={
            "event": "improvement_experiment",
            "context": {
                "proposal_id": proposal.id,
                "verdict": comparison["verdict"],
                "gated": approval is not None,
            },
        },
    )
    return proposal, approval


async def propose_model_candidates(
    session: AsyncSession, *, suite_id: str | None = None
) -> list[ImprovementProposal]:
    """Autonomously propose adopting other available models as the default.

    For each available model that isn't the current default and doesn't already
    have an open proposal, create a proposal (candidate vs current default) on an
    eval suite. Creating it fires the auto-experiment, so ATLAS reaches a verdict
    and an approval gate without any human input — only the final apply stays
    human-gated. A no-op when there is no eval suite or no alternative model.
    """

    from app.services import eval_service, registry_service

    settings = await settings_service.get_effective_settings(session)
    default = settings.default_model

    if suite_id:
        suite = await eval_service.get_suite(session, suite_id)
    else:
        suites = await eval_service.list_suites(session)
        suite = suites[0] if suites else None
    if suite is None:
        return []

    models = [m for m in await registry_service.list_models(session) if m.available]
    open_states = {
        ProposalStatus.DRAFT.value,
        ProposalStatus.EXPERIMENTED.value,
        ProposalStatus.APPROVED.value,
    }
    taken = {
        p.candidate_model
        for p in await list_proposals(session)
        if p.status in open_states and p.candidate_model
    }

    from app.ai.echo import ECHO_MODEL

    created: list[ImprovementProposal] = []
    for model in models:
        name = model.name
        # Never propose the echo/test stub as the default, nor the current
        # default, nor a candidate that already has an open proposal.
        if not name or name in (default, ECHO_MODEL) or name in taken:
            continue
        proposal = await create_proposal(
            session,
            title=f"Auto: adopt {name} as default",
            description="Autonomously proposed by ATLAS (candidate vs current default).",
            category=ProposalCategory.MODEL.value,
            suite_id=suite.id,
            baseline_model=default or None,
            candidate_model=name,
        )
        created.append(proposal)
        taken.add(name)

    if created:
        logger.info(
            "autonomous proposals created",
            extra={"event": "auto_propose", "context": {"count": len(created)}},
        )
    return created


async def propose_now(session: AsyncSession) -> list[ImprovementProposal]:
    """On-demand proposer: refresh models, seed a starter suite if none, propose.

    Used by the "Generate proposals now" button so it works out of the box even on
    a fresh install. Returns the proposals created (empty if there is no
    alternative model to try).
    """

    from app.services import eval_service, registry_service

    try:
        await registry_service.refresh_models(session)
    except Exception:  # noqa: BLE001 - discovery is best-effort (may be offline)
        logger.warning("model refresh failed", extra={"event": "propose_refresh"})

    suites = await eval_service.list_suites(session)
    if not suites:
        suite = await eval_service.create_suite(
            session,
            name="Starter suite",
            description="Auto-created starter eval suite — edit its cases on the Evals page.",
        )
        await eval_service.add_case(
            session,
            suite_id=suite.id,
            input="Reply with the single word: ready",
            expected_substrings=["ready"],
        )

    return await propose_model_candidates(session)


async def apply_proposal(
    session: AsyncSession, proposal: ImprovementProposal
) -> ImprovementProposal:
    """Apply an **approved** proposal (governed). Refuses unless APPROVED."""

    if proposal.status != ProposalStatus.APPROVED.value:
        raise ImprovementStateError("Proposal is not approved yet; a human must approve it first")

    change = proposal.change or {}
    if "default_model" in change and change["default_model"]:
        await settings_service.set_ai_config(
            {"default_model": change["default_model"]}, session
        )
    # Other categories record the applied intent; concrete appliers plug in here.

    proposal.status = ProposalStatus.APPLIED.value
    await session.commit()
    await session.refresh(proposal)
    logger.info(
        "improvement applied",
        extra={
            "event": "improvement_applied",
            "context": {"proposal_id": proposal.id, "change": change},
        },
    )
    return proposal
