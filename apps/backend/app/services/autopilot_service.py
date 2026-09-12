"""Autopilot summary: one read-only view of what ATLAS does on its own.

Aggregates the autonomous loops (model proposer, experiments, self-healing,
code self-review), a recent-activity feed, and the short list of things still
waiting on a human. Read-only — it never triggers or changes anything.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.improvement import ProposalStatus
from app.models.maintenance import IssueStatus
from app.services import (
    approval_service,
    finetune_service,
    improvement_service,
    maintenance_service,
)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def automation_state() -> dict[str, Any]:
    """Which autonomous loops are on, and how often they run."""

    s = get_settings()
    return {
        "auto_propose": s.improvement_auto_propose_enabled,
        "auto_experiment": s.improvement_auto_experiment_enabled,
        "auto_fix": s.maintenance_auto_fix_enabled,
        "self_review": s.code_review_auto_enabled,
        "propose_interval_s": s.improvement_auto_propose_interval,
        "self_review_interval_s": s.code_review_interval,
    }


async def pending_actions(
    session: AsyncSession,
    proposals: list[Any],
    approvals: list[Any],
    issues: list[Any],
) -> list[dict[str, Any]]:
    """The concrete decisions still waiting on a human, with the ids needed to act
    on them directly (approve/reject, evaluate a canary, roll out an approved
    change, dismiss a code finding) — so Autopilot is not just a view."""

    from app.ai.echo import ECHO_MODEL

    by_id = {p.id: p for p in proposals}
    actions: list[dict[str, Any]] = []
    for ap in approvals:
        is_model = ap.subject_type == "improvement_proposal"
        proposal = by_id.get(ap.subject_id or "") if is_model else None
        # Never surface a decision to adopt the echo/test stub as default, nor a
        # stale model change whose experiment was not actually an improvement
        # (older gates created before improvement-only gating).
        if is_model and proposal is not None:
            if proposal.candidate_model == ECHO_MODEL:
                continue
            if proposal.recommendation not in (None, "improvement"):
                continue
        actions.append(
            {
                "id": ap.id,
                "action": "decide",
                "kind": "model" if is_model else "code",
                "title": (proposal.title if proposal else None) or ap.action or "Pending change",
                "detail": ap.action,
                "approval_id": ap.id,
                "proposal_id": ap.subject_id if is_model else None,
                "issue_id": None,
            }
        )
    # Open code findings from self-review: real, actionable observations. ATLAS
    # cannot yet synthesize a repo-grounded patch, so the honest decision is to
    # review the file or dismiss the finding.
    for issue in issues:
        if issue.service == "self-review" and issue.status == IssueStatus.OPEN.value:
            actions.append(
                {
                    "id": f"issue-{issue.id}",
                    "action": "review_code",
                    "kind": "code",
                    "title": issue.title,
                    "detail": f"severity {issue.severity}",
                    "approval_id": None,
                    "proposal_id": None,
                    "issue_id": issue.id,
                }
            )
    for p in proposals:
        if p.status == ProposalStatus.CANARY.value:
            actions.append(
                {
                    "id": f"canary-{p.id}",
                    "action": "evaluate_canary",
                    "kind": "canary",
                    "title": p.title,
                    "detail": "canary live — run the health gate",
                    "approval_id": None,
                    "proposal_id": p.id,
                }
            )
        elif p.status == ProposalStatus.APPROVED.value:
            actions.append(
                {
                    "id": f"rollout-{p.id}",
                    "action": "rollout",
                    "kind": "model",
                    "title": p.title,
                    "detail": "approved — start a canary or apply",
                    "approval_id": None,
                    "proposal_id": p.id,
                }
            )
    return actions


async def summary(session: AsyncSession, *, limit: int = 20) -> dict[str, Any]:
    proposals = await improvement_service.list_proposals(session)
    issues = await maintenance_service.list_issues(session)
    jobs = await finetune_service.list_jobs(session)
    pending_approvals = await approval_service.list_approvals(session, status="PENDING")
    actions = await pending_actions(session, proposals, pending_approvals, issues)

    activity: list[dict[str, Any]] = []
    for p in proposals:
        activity.append(
            {
                "kind": "proposal",
                "title": p.title,
                "status": p.status,
                "detail": p.recommendation or (p.candidate_model or ""),
                "when": _iso(p.updated_at),
            }
        )
    for i in issues:
        activity.append(
            {
                "kind": "self-review" if i.service == "self-review" else "maintenance",
                "title": i.title,
                "status": i.status,
                "detail": f"severity {i.severity}",
                "when": _iso(i.last_seen),
            }
        )
    for j in jobs:
        activity.append(
            {
                "kind": "finetune",
                "title": f"Fine-tune {j.adapter_name}",
                "status": j.status,
                "detail": f"{j.example_count} examples",
                "when": _iso(j.updated_at),
            }
        )
    activity.sort(key=lambda a: a["when"] or "", reverse=True)

    canary_live = sum(1 for p in proposals if p.status == ProposalStatus.CANARY.value)
    open_issues = sum(1 for i in issues if i.status == IssueStatus.OPEN.value)
    self_review_issues = sum(1 for i in issues if i.service == "self-review")

    return {
        "automation": automation_state(),
        "pending": {
            "approvals": len(pending_approvals),
            "canary_awaiting_eval": canary_live,
            "open_issues": open_issues,
        },
        "counts": {
            "proposals": len(proposals),
            "issues": len(issues),
            "self_review_issues": self_review_issues,
            "finetune_jobs": len(jobs),
        },
        "actions": actions,
        "activity": activity[:limit],
    }
