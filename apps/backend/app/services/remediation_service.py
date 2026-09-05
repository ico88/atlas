"""Auto-remediation (ROADMAP PR 25): guided diagnosis, remedies, quarantine.

Turns a compliance drift report into safe actions:
* **remediate** — re-align a version-drifted node to the desired version (the
  agent applies `desired_version` and reports back);
* **quarantine** — take a node out of scheduling;
* **reinstate** — return a recovered node to service.

`diagnose` is pure. `auto_remediate` is deliberately conservative: it only
auto-fixes version drift on online nodes; offline / missing-capability cases are
surfaced for a human. Every action is recorded in `remediation_events`.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.node import Node
from app.models.remediation import RemediationAction, RemediationEvent
from app.services import compliance_service

logger = logging.getLogger(__name__)


class RemediationError(RuntimeError):
    """Raised when a remediation target cannot be found."""


def diagnose(node_report: dict[str, Any]) -> dict[str, Any]:
    """Guided diagnosis for one node's drift report. Pure/testable."""

    issues = node_report.get("issues") or []
    if node_report.get("compliant"):
        return {"diagnosis": "Compliant.", "recommended_action": None, "auto": False}
    if node_report.get("quarantined"):
        return {
            "diagnosis": "Node is quarantined (excluded from scheduling).",
            "recommended_action": RemediationAction.REINSTATE.value,
            "auto": False,
        }
    if any(i.startswith("version") for i in issues):
        return {
            "diagnosis": "Node is running a different version than desired.",
            "recommended_action": RemediationAction.REMEDIATE.value,
            "auto": True,  # safe to auto-fix (re-align to desired version)
        }
    if "offline" in issues:
        return {
            "diagnosis": "Node is offline; it cannot be fixed remotely. Investigate the host, "
            "or quarantine it if it stays down.",
            "recommended_action": RemediationAction.QUARANTINE.value,
            "auto": False,
        }
    if any(i.startswith("missing capability") for i in issues):
        return {
            "diagnosis": "Node lacks a required capability; reconfigure the node agent.",
            "recommended_action": None,
            "auto": False,
        }
    return {"diagnosis": "Non-compliant.", "recommended_action": None, "auto": False}


async def _node(session: AsyncSession, node_ref: str) -> Node:
    node = await node_service_get(session, node_ref)
    if node is None:
        raise RemediationError(f"Node '{node_ref}' not found")
    return node


async def node_service_get(session: AsyncSession, node_ref: str) -> Node | None:
    from app.services import node_service

    return await node_service.get_node_by_ref(session, node_ref)


async def _record(
    session: AsyncSession, node_ref: str, action: str, reason: str | None, automatic: bool
) -> RemediationEvent:
    ev = RemediationEvent(
        node_ref=node_ref, action=action, reason=reason, automatic=automatic
    )
    session.add(ev)
    return ev


async def remediate(
    session: AsyncSession, node_ref: str, *, target_version: str, automatic: bool = False
) -> RemediationEvent:
    node = await _node(session, node_ref)
    node.desired_version = target_version or None
    ev = await _record(
        session, node_ref, RemediationAction.REMEDIATE.value,
        f"re-align to {target_version or 'desired'}", automatic,
    )
    await session.commit()
    await session.refresh(ev)
    logger.info("node remediated", extra={"event": "remediate", "context": {"node": node_ref}})
    return ev


async def quarantine(
    session: AsyncSession, node_ref: str, *, reason: str | None = None, automatic: bool = False
) -> RemediationEvent:
    node = await _node(session, node_ref)
    node.quarantined = True
    ev = await _record(session, node_ref, RemediationAction.QUARANTINE.value, reason, automatic)
    await session.commit()
    await session.refresh(ev)
    logger.warning("node quarantined", extra={"event": "quarantine", "context": {"node": node_ref}})
    return ev


async def reinstate(
    session: AsyncSession, node_ref: str, *, automatic: bool = False
) -> RemediationEvent:
    node = await _node(session, node_ref)
    node.quarantined = False
    ev = await _record(
        session, node_ref, RemediationAction.REINSTATE.value, "returned to service", automatic
    )
    await session.commit()
    await session.refresh(ev)
    logger.info("node reinstated", extra={"event": "reinstate", "context": {"node": node_ref}})
    return ev


async def auto_remediate(session: AsyncSession) -> list[dict[str, Any]]:
    """Apply the safe recommended action to each drifted node. Returns what it did."""

    report = await compliance_service.fleet_report(session)
    target = (report["desired"].get("target_version") or "").strip()
    done: list[dict[str, Any]] = []
    for nr in report["nodes"]:
        dx = diagnose(nr)
        if dx["auto"] and dx["recommended_action"] == RemediationAction.REMEDIATE.value and target:
            await remediate(session, nr["node_ref"], target_version=target, automatic=True)
            done.append({"node_ref": nr["node_ref"], "action": "remediate"})
    logger.info("auto-remediation sweep", extra={"event": "auto_remediate",
                "context": {"count": len(done)}})
    return done


async def list_events(session: AsyncSession, *, limit: int = 100) -> list[RemediationEvent]:
    result = await session.execute(
        select(RemediationEvent).order_by(RemediationEvent.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())
