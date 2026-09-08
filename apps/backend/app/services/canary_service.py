"""Canary rollout with health gate + auto-rollback (ROADMAP R6).

Applying an approved improvement no longer flips the default instantly. Instead:

1. **start** — record the current value as the rollback point, apply the
   candidate, and enter CANARY (the change is live for a watched window).
2. **evaluate** (the health gate) — compare the candidate against the baseline on
   measured quality (from evals) and control-plane health; **promote** to APPLIED
   if healthy, or **auto-rollback** to the previous value if it regressed.

The decision is a pure function so it is unit-tested; nothing is applied outside
the guardrails, and a regression reverts itself.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.improvement import ImprovementProposal, ProposalStatus
from app.services import learning_service, settings_service, slo_service

logger = logging.getLogger(__name__)


class CanaryError(RuntimeError):
    pass


def decide(
    *,
    baseline_quality: float | None,
    candidate_quality: float | None,
    healthy: bool,
    tolerance: float,
) -> tuple[str, str]:
    """Pure health gate. Returns (decision, reason): 'promote' or 'rollback'."""

    if not healthy:
        return "rollback", "control plane unhealthy during canary"
    if (
        baseline_quality is not None
        and candidate_quality is not None
        and candidate_quality < baseline_quality - tolerance
    ):
        return (
            "rollback",
            f"quality regressed {baseline_quality:.3f} -> {candidate_quality:.3f}",
        )
    return "promote", "healthy and no measured regression"


async def start(session: AsyncSession, proposal: ImprovementProposal) -> ImprovementProposal:
    """Begin a canary for an APPROVED proposal: apply the candidate, remember the
    rollback point, and record the baseline quality signal."""

    if proposal.status != ProposalStatus.APPROVED.value:
        raise CanaryError("Proposal must be APPROVED before a canary")
    change = dict(proposal.change or {})
    if not change.get("default_model"):
        raise CanaryError("Canary currently supports default_model changes only")

    effective = await settings_service.get_effective_settings()
    previous = effective.default_model or ""
    quality = await learning_service.model_quality(session)

    # Apply the candidate now (the canary window is live).
    await settings_service.set_ai_config({"default_model": change["default_model"]}, session)

    canary: dict[str, Any] = {
        "previous_default_model": previous,
        "candidate_default_model": change["default_model"],
        "baseline_quality": quality.get(previous),
    }
    comparison = dict(proposal.comparison or {})
    comparison["canary"] = canary
    proposal.comparison = comparison
    proposal.status = ProposalStatus.CANARY.value
    await session.commit()
    await session.refresh(proposal)
    logger.info(
        "canary started",
        extra={"event": "canary_start", "context": {"proposal_id": proposal.id, **canary}},
    )
    return proposal


async def evaluate(session: AsyncSession, proposal: ImprovementProposal) -> ImprovementProposal:
    """Run the health gate; promote (APPLIED) or auto-rollback (ROLLED_BACK)."""

    if proposal.status != ProposalStatus.CANARY.value:
        raise CanaryError("Proposal is not in a canary")
    canary = (proposal.comparison or {}).get("canary") or {}
    settings = get_settings()

    quality = await learning_service.model_quality(session)
    candidate = str(canary.get("candidate_default_model") or "")
    previous = str(canary.get("previous_default_model") or "")
    slo = await slo_service.report(session)
    healthy = all(
        s["ok"] for s in slo["slos"] if s["name"] == "control_plane_healthy"
    )

    decision, reason = decide(
        baseline_quality=canary.get("baseline_quality"),
        candidate_quality=quality.get(candidate),
        healthy=healthy,
        tolerance=settings.canary_quality_tolerance,
    )

    # The rollback restore commits internally (expiring in-place JSON edits), so
    # build the final canary dict and assign proposal.comparison once, afterwards.
    if decision == "rollback":
        await settings_service.set_ai_config({"default_model": previous}, session)
        proposal.status = ProposalStatus.ROLLED_BACK.value
    else:
        proposal.status = ProposalStatus.APPLIED.value

    final_canary = {**canary, "decision": decision, "reason": reason}
    proposal.comparison = {**(proposal.comparison or {}), "canary": final_canary}
    await session.commit()
    await session.refresh(proposal)
    logger.info(
        "canary evaluated",
        extra={
            "event": "canary_eval",
            "context": {"proposal_id": proposal.id, "decision": decision, "reason": reason},
        },
    )
    return proposal
