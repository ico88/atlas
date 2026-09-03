"""Semi-automatic advancement of the maintenance & improvement loops.

The goal is to remove busywork without removing governance: the *analysis* and
*experiment* phases run by themselves in the background, so a human is left with
only the approve / apply decision. Irreversible steps (opening a PR, changing the
default model) are never performed here — they stay behind the human approval
gate.

Each background worker owns its own DB session (it runs detached from any HTTP
request) and is best-effort: a failure is logged and never propagates.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import get_sessionmaker
from app.models.improvement import ProposalStatus
from app.models.maintenance import IssueStatus, RunStatus

logger = logging.getLogger(__name__)

# Strong references so detached workers are not garbage-collected mid-flight.
_BACKGROUND: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _BACKGROUND.add(task)
    task.add_done_callback(_BACKGROUND.discard)


# --------------------------------------------------------------------------- #
# maintenance: ingest -> analyze -> sandbox-validated fix (awaiting approval)
# --------------------------------------------------------------------------- #
async def advance_issue(session: AsyncSession, issue_id: str) -> bool:
    """Advance an OPEN issue to a fix that is awaiting approval. Returns did-work.

    Idempotent and conservative: skips issues that already have a run awaiting or
    past approval, so it never stacks duplicate fixes or approval gates.
    """

    from app.services import maintenance_service

    issue = await maintenance_service.get_issue(session, issue_id)
    if issue is None:
        return False
    if issue.status not in (IssueStatus.OPEN.value, IssueStatus.ANALYZING.value):
        return False
    # Don't re-propose if a run is already awaiting or past the approval gate.
    blocking = {
        RunStatus.NEEDS_APPROVAL.value,
        RunStatus.APPROVED.value,
        RunStatus.PR_OPENED.value,
    }
    if any(r.status in blocking for r in issue.runs):
        return False

    await maintenance_service.create_fix(session, issue)
    return True


async def _advance_issue_bg(issue_id: str) -> None:
    async with get_sessionmaker()() as session:
        try:
            await advance_issue(session, issue_id)
        except Exception:  # noqa: BLE001 - best-effort background work
            logger.warning(
                "auto issue advance failed",
                extra={"event": "auto_issue_error", "context": {"issue_id": issue_id}},
            )


def maybe_advance_issue(issue_id: str) -> None:
    """Fire-and-forget: prepare a fix for a freshly-seen issue, if auto is on."""

    if get_settings().maintenance_auto_fix_enabled:
        _spawn(_advance_issue_bg(issue_id))


# --------------------------------------------------------------------------- #
# improvement: create -> run experiment (awaiting approval)
# --------------------------------------------------------------------------- #
async def advance_proposal(session: AsyncSession, proposal_id: str) -> bool:
    """Run the experiment for a DRAFT proposal that has a suite. Returns did-work."""

    from app.services import improvement_service

    proposal = await improvement_service.get_proposal(session, proposal_id)
    if proposal is None:
        return False
    if proposal.status != ProposalStatus.DRAFT.value or not proposal.suite_id:
        return False

    await improvement_service.run_experiment(session, proposal)
    return True


async def _advance_proposal_bg(proposal_id: str) -> None:
    async with get_sessionmaker()() as session:
        try:
            await advance_proposal(session, proposal_id)
        except Exception:  # noqa: BLE001 - best-effort background work
            logger.warning(
                "auto proposal advance failed",
                extra={
                    "event": "auto_proposal_error",
                    "context": {"proposal_id": proposal_id},
                },
            )


def maybe_advance_proposal(proposal_id: str) -> None:
    """Fire-and-forget: run the experiment for a new proposal, if auto is on."""

    if get_settings().improvement_auto_experiment_enabled:
        _spawn(_advance_proposal_bg(proposal_id))
