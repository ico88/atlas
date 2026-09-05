"""Fleet deployment orchestration (ROADMAP PR 21 / PR 22).

Rolls a target version out to the fleet: a canary wave first, a **health gate**
before promoting the rest, a rolling wave, and **rollback** on any failure.
Offline nodes are skipped (reconciled later); nodes below the compatibility floor
are skipped with a reason.

Planning (`plan_targets`) and version comparison are pure functions so the wave
selection and gate logic are unit-testable without a live fleet. The node agent
applies `node.desired_version` and reports the result back via heartbeat; here
`report_result` records that report.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deployment import (
    Deployment,
    DeploymentStatus,
    DeploymentTarget,
    TargetStatus,
)
from app.models.node import Node
from app.services import node_service

logger = logging.getLogger(__name__)


class DeploymentStateError(RuntimeError):
    """Raised when an action is requested in a state that does not allow it."""


def version_tuple(v: str | None) -> tuple[int, ...]:
    """Best-effort numeric version tuple (e.g. 'v1.2.3' -> (1, 2, 3))."""

    if not v:
        return ()
    return tuple(int(n) for n in re.findall(r"\d+", v))


def is_compatible(node_version: str | None, min_compatible: str | None) -> bool:
    """A node is compatible if it has no floor, no version, or version >= floor."""

    if not min_compatible or not node_version:
        return True
    return version_tuple(node_version) >= version_tuple(min_compatible)


@dataclass
class TargetPlan:
    node_pk: str
    node_ref: str
    from_version: str | None
    wave: str  # canary | rollout
    status: str


def plan_targets(
    nodes: list[dict],
    *,
    canary_count: int,
    min_compatible: str | None = None,
) -> list[TargetPlan]:
    """Decide each node's wave/status. ``nodes`` items: {pk, ref, version, online}.

    Offline → SKIPPED_OFFLINE; below the compatibility floor → INCOMPATIBLE; the
    rest are eligible, the first ``canary_count`` forming the canary wave.
    """

    plans: list[TargetPlan] = []
    eligible: list[dict] = []
    for n in nodes:
        if not n.get("online"):
            plans.append(TargetPlan(n["pk"], n["ref"], n.get("version"), "canary",
                                    TargetStatus.SKIPPED_OFFLINE.value))
        elif not is_compatible(n.get("version"), min_compatible):
            plans.append(TargetPlan(n["pk"], n["ref"], n.get("version"), "canary",
                                    TargetStatus.INCOMPATIBLE.value))
        else:
            eligible.append(n)

    cap = max(0, canary_count)
    for i, n in enumerate(eligible):
        wave = "canary" if i < cap else "rollout"
        plans.append(TargetPlan(n["pk"], n["ref"], n.get("version"), wave,
                                TargetStatus.PENDING.value))
    return plans


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #
def _wave(targets: list[DeploymentTarget], wave: str) -> list[DeploymentTarget]:
    return [t for t in targets if t.wave == wave and t.status not in (
        TargetStatus.SKIPPED_OFFLINE.value, TargetStatus.INCOMPATIBLE.value)]


async def _set_desired(session: AsyncSession, node_pk: str, version: str | None) -> None:
    node = await session.get(Node, node_pk)
    if node is not None:
        node.desired_version = version


async def create_deployment(
    session: AsyncSession,
    *,
    target_version: str,
    canary_count: int = 1,
    min_compatible: str | None = None,
    note: str | None = None,
) -> Deployment:
    """Plan a rollout and start the canary wave."""

    nodes = await node_service.list_nodes(session)
    infos = [
        {
            "pk": n.id,
            "ref": n.node_id,
            "version": n.version,
            "online": node_service.is_online(n),
        }
        for n in nodes
    ]
    plans = plan_targets(infos, canary_count=canary_count, min_compatible=min_compatible)

    previous = next((p.from_version for p in plans if p.from_version), None)
    dep = Deployment(
        target_version=target_version,
        previous_version=previous,
        strategy="canary",
        canary_count=canary_count,
        status=DeploymentStatus.CANARY.value,
        note=note,
    )
    session.add(dep)
    await session.flush()

    for p in plans:
        status = p.status
        # Start the canary wave immediately (desired version set now).
        if p.wave == "canary" and status == TargetStatus.PENDING.value:
            status = TargetStatus.UPDATING.value
            await _set_desired(session, p.node_pk, target_version)
        session.add(
            DeploymentTarget(
                deployment_id=dep.id,
                node_pk=p.node_pk,
                node_ref=p.node_ref,
                from_version=p.from_version,
                wave=p.wave,
                status=status,
            )
        )
    await session.commit()
    await session.refresh(dep)
    logger.info(
        "deployment created",
        extra={"event": "deploy_created",
               "context": {"id": dep.id, "target": target_version}},
    )
    return await get_deployment(session, dep.id)  # type: ignore[return-value]


async def report_result(
    session: AsyncSession, deployment_id: str, node_ref: str, *, version: str, healthy: bool
) -> DeploymentTarget:
    """Record a node's post-update report (as the agent would send via heartbeat)."""

    dep = await get_deployment(session, deployment_id)
    if dep is None:
        raise DeploymentStateError("Deployment not found")
    target = next((t for t in dep.targets if t.node_ref == node_ref), None)
    if target is None:
        raise DeploymentStateError(f"Node '{node_ref}' is not part of this deployment")

    ok = healthy and version == dep.target_version
    target.status = TargetStatus.HEALTHY.value if ok else TargetStatus.FAILED.value
    target.detail = None if ok else f"reported version={version} healthy={healthy}"
    node = await session.get(Node, target.node_pk)
    if node is not None:
        node.version = version
    await session.commit()
    await session.refresh(target)
    return target


async def advance(session: AsyncSession, deployment_id: str) -> Deployment:
    """Apply the health gate and move the rollout forward (or roll back)."""

    dep = await get_deployment(session, deployment_id)
    if dep is None:
        raise DeploymentStateError("Deployment not found")
    if dep.status in (DeploymentStatus.COMPLETED.value, DeploymentStatus.ROLLED_BACK.value):
        return dep

    canary = _wave(dep.targets, "canary")
    rollout = _wave(dep.targets, "rollout")

    def _all(ts: list[DeploymentTarget], s: str) -> bool:
        return bool(ts) and all(t.status == s for t in ts)

    def _any(ts: list[DeploymentTarget], s: str) -> bool:
        return any(t.status == s for t in ts)

    if dep.status == DeploymentStatus.CANARY.value:
        if _any(canary, TargetStatus.FAILED.value):
            await _rollback(session, dep)
        elif not canary or _all(canary, TargetStatus.HEALTHY.value):
            # Gate passed → promote the rollout wave (or finish if there is none).
            if rollout:
                for t in rollout:
                    if t.status == TargetStatus.PENDING.value:
                        t.status = TargetStatus.UPDATING.value
                        await _set_desired(session, t.node_pk, dep.target_version)
                dep.status = DeploymentStatus.ROLLING.value
            else:
                dep.status = DeploymentStatus.COMPLETED.value
            await session.commit()
    elif dep.status == DeploymentStatus.ROLLING.value:
        if _any(rollout, TargetStatus.FAILED.value):
            await _rollback(session, dep)
        elif _all(rollout, TargetStatus.HEALTHY.value):
            dep.status = DeploymentStatus.COMPLETED.value
            await session.commit()

    await session.refresh(dep)
    logger.info(
        "deployment advanced",
        extra={"event": "deploy_advanced", "context": {"id": dep.id, "status": dep.status}},
    )
    return dep


async def _rollback(session: AsyncSession, dep: Deployment) -> None:
    """Revert every node that was touched back to its previous version."""

    for t in dep.targets:
        if t.status in (TargetStatus.SKIPPED_OFFLINE.value, TargetStatus.INCOMPATIBLE.value):
            continue
        await _set_desired(session, t.node_pk, t.from_version)
    dep.status = DeploymentStatus.ROLLED_BACK.value
    dep.note = (dep.note + " | " if dep.note else "") + "rolled back after a failed health check"
    await session.commit()
    logger.warning(
        "deployment rolled back",
        extra={"event": "deploy_rolled_back", "context": {"id": dep.id}},
    )


async def list_deployments(session: AsyncSession, *, limit: int = 50) -> list[Deployment]:
    from sqlalchemy.orm import selectinload

    result = await session.execute(
        select(Deployment)
        .options(selectinload(Deployment.targets))
        .order_by(Deployment.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_deployment(session: AsyncSession, deployment_id: str) -> Deployment | None:
    from sqlalchemy.orm import selectinload

    result = await session.execute(
        select(Deployment)
        .where(Deployment.id == deployment_id)
        .options(selectinload(Deployment.targets))
    )
    return result.scalar_one_or_none()
