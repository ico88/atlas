"""Manual escalation workflow (spec §10, M7).

Prepares a copy-paste package for ChatGPT/Claude, imports the pasted response as
UNTRUSTED data, and lets a human validate it before it can become a controlled
change. The response is never executed automatically.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.escalation.package import EscalationContext, build_package
from app.models.base import new_uuid
from app.models.escalation import Escalation, EscalationStatus, EscalationTarget
from app.models.maintenance import MaintenanceIssue, MaintenanceRun

logger = logging.getLogger(__name__)

_VALID_TARGETS = {EscalationTarget.CHATGPT.value, EscalationTarget.CLAUDE.value}


def _normalize_target(target: str) -> str:
    return target if target in _VALID_TARGETS else EscalationTarget.CHATGPT.value


async def prepare(
    session: AsyncSession,
    *,
    objective: str,
    target: str = EscalationTarget.CHATGPT.value,
    subject_type: str = "manual",
    subject_id: str | None = None,
    context: EscalationContext | None = None,
    correlation_id: str | None = None,
) -> Escalation:
    target = _normalize_target(target)
    corr = correlation_id or new_uuid()
    package = build_package(
        objective=objective, target=target, correlation_id=corr, context=context
    )
    escalation = Escalation(
        subject_type=subject_type,
        subject_id=subject_id,
        target=target,
        objective=objective,
        correlation_id=corr,
        package=package,
        status=EscalationStatus.PREPARED.value,
    )
    session.add(escalation)
    await session.commit()
    await session.refresh(escalation)
    logger.info(
        "escalation prepared",
        extra={"event": "escalation_prepared", "context": {"id": escalation.id, "target": target}},
    )
    return escalation


async def prepare_for_issue(
    session: AsyncSession, issue: MaintenanceIssue, *, target: str = EscalationTarget.CHATGPT.value
) -> Escalation:
    """Build an escalation from a maintenance issue's context (§10, §11)."""

    latest_run = (
        await session.execute(
            select(MaintenanceRun)
            .where(MaintenanceRun.issue_id == issue.id)
            .order_by(MaintenanceRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    sample = issue.sample or {}
    context = EscalationContext(
        project_context=f"Service: {issue.service or 'unknown'}; severity: {issue.severity}.",
        logs=str(sample.get("message") or "")
        + (f"\nevent: {sample.get('event')}" if sample.get("event") else ""),
        hypothesis=(latest_run.analysis or "" if latest_run else ""),
        tests_executed=(
            latest_run.tests_summary or "" if latest_run else ""
        ),
    )
    return await prepare(
        session,
        objective=f"Fix issue: {issue.title}",
        target=target,
        subject_type="maintenance_issue",
        subject_id=issue.id,
        context=context,
        correlation_id=issue.fingerprint[:36],
    )


async def list_escalations(
    session: AsyncSession, *, status: str | None = None
) -> list[Escalation]:
    query = select(Escalation).order_by(Escalation.created_at.desc())
    if status:
        query = query.where(Escalation.status == status)
    return list((await session.execute(query)).scalars().all())


async def get_escalation(session: AsyncSession, escalation_id: str) -> Escalation | None:
    return await session.get(Escalation, escalation_id)


def _auto_checks(response: str) -> dict[str, object]:
    """Lightweight, non-authoritative signals about a pasted response.

    These are hints for the human reviewer only — the response stays UNTRUSTED
    until a person validates it. They never gate or auto-apply anything.
    """

    lowered = response.lower()
    return {
        "length": len(response),
        "contains_diff": ("diff --git" in lowered or "@@" in response or "```" in response),
        "mentions_secret": any(
            w in lowered for w in ("password", "api_key", "secret", "token", "-----begin")
        ),
        "empty": not response.strip(),
    }


async def import_response(
    session: AsyncSession, escalation: Escalation, response: str
) -> Escalation:
    """Store the pasted response as UNTRUSTED and record automatic hints."""

    escalation.response = response
    escalation.status = EscalationStatus.RESPONSE_IMPORTED.value
    escalation.validation = {"trusted": False, "auto_checks": _auto_checks(response)}
    await session.commit()
    await session.refresh(escalation)
    logger.info(
        "escalation response imported (untrusted)",
        extra={"event": "escalation_imported", "context": {"id": escalation.id}},
    )
    return escalation


async def validate(
    session: AsyncSession,
    escalation: Escalation,
    *,
    approved: bool,
    notes: str | None = None,
    decided_by: str = "operator",
) -> Escalation:
    escalation.status = (
        EscalationStatus.VALIDATED.value if approved else EscalationStatus.REJECTED.value
    )
    validation = dict(escalation.validation or {})
    validation.update({"trusted": approved, "decided_by": decided_by, "notes": notes})
    escalation.validation = validation
    await session.commit()
    await session.refresh(escalation)
    logger.info(
        "escalation validated",
        extra={
            "event": "escalation_validated",
            "context": {"id": escalation.id, "approved": approved},
        },
    )
    return escalation
