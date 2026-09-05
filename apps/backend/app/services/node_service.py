"""Node registration, heartbeat and liveness helpers (spec §8)."""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.base import utcnow
from app.models.node import Node
from app.models.task import Task, TaskStatus
from app.schemas.node import NodeHeartbeat, NodeRegister
from app.services import task_service

logger = logging.getLogger(__name__)


def is_online(node: Node) -> bool:
    """A node is online if it reported a heartbeat recently enough."""

    if node.last_heartbeat is None or node.status != "online":
        return False
    threshold = timedelta(seconds=get_settings().node_offline_after_seconds)
    last = node.last_heartbeat
    now = utcnow()
    # Tolerate naive datetimes coming back from SQLite.
    if last.tzinfo is None:
        now = now.replace(tzinfo=None)
    return (now - last) <= threshold


async def get_node_by_ref(session: AsyncSession, ref: str) -> Node | None:
    """Look up a node by its database id or its logical ``node_id``."""

    node = await session.get(Node, ref)
    if node is not None:
        return node
    result = await session.execute(select(Node).where(Node.node_id == ref))
    return result.scalar_one_or_none()


async def list_nodes(session: AsyncSession) -> list[Node]:
    result = await session.execute(select(Node).order_by(Node.created_at.asc()))
    return list(result.scalars().all())


async def register_node(session: AsyncSession, data: NodeRegister) -> Node:
    """Create or update a node (idempotent upsert by ``node_id``)."""

    result = await session.execute(select(Node).where(Node.node_id == data.node_id))
    node = result.scalar_one_or_none()
    now = utcnow()

    if node is None:
        node = Node(node_id=data.node_id)
        session.add(node)

    node.hostname = data.hostname
    node.label = data.label
    node.version = data.version
    if data.capabilities is not None:
        node.capabilities = data.capabilities
    if data.hardware is not None:
        node.hardware = data.hardware
    node.status = "online"
    node.last_heartbeat = now

    await session.commit()
    await session.refresh(node)
    logger.info(
        "node registered",
        extra={"event": "node_registered", "context": {"node_id": node.node_id}},
    )
    return node


def node_capabilities(node: Node) -> list[str]:
    return [k for k, v in (node.capabilities or {}).items() if v]


async def claim_task(session: AsyncSession, node: Node) -> Task | None:
    """Atomically claim the next QUEUED task matching the node's capabilities.

    Uses a status-guarded UPDATE as an optimistic lock so concurrent claims from
    multiple nodes never double-assign a task (portable across PostgreSQL/SQLite).
    """

    # Quarantined nodes (PR 25) are excluded from scheduling until reinstated.
    if getattr(node, "quarantined", False):
        return None

    caps = node_capabilities(node)
    if not caps:
        return None

    stmt = (
        select(Task)
        .where(Task.status == TaskStatus.QUEUED.value, Task.required_capability.in_(caps))
        .order_by(Task.priority.desc(), Task.created_at.asc())
        .limit(10)
    )
    candidates = list((await session.execute(stmt)).scalars().all())
    now = utcnow()
    for task in candidates:
        result = await session.execute(
            update(Task)
            .where(Task.id == task.id, Task.status == TaskStatus.QUEUED.value)
            .values(status=TaskStatus.RUNNING.value, assigned_node_id=node.id, started_at=now)
        )
        if result.rowcount and result.rowcount > 0:
            await session.commit()
            claimed = await session.get(Task, task.id)
            assert claimed is not None
            # Grant a lease so a crashed node's task is reclaimed (ROADMAP PR 8).
            from app.services import scheduler_service

            await scheduler_service.acquire_lease(session, claimed)
            await task_service.record_event(
                session,
                claimed,
                "status_changed",
                status=TaskStatus.RUNNING,
                message=f"Claimed by node {node.node_id}",
                data={"node_id": node.node_id},
            )
            await session.commit()
            await session.refresh(claimed)
            logger.info(
                "task claimed by node",
                extra={"event": "node_claimed", "context": {"node_id": node.node_id}},
            )
            return claimed
    return None


async def heartbeat(session: AsyncSession, node: Node, data: NodeHeartbeat) -> Node:
    node.status = data.status or "online"
    node.last_heartbeat = utcnow()
    if data.health is not None:
        # Merge health into the hardware/health snapshot without losing capabilities.
        hardware = dict(node.hardware or {})
        hardware["health"] = data.health
        node.hardware = hardware
    await session.commit()
    await session.refresh(node)
    # Record a telemetry sample (ROADMAP PR 12); never let it break heartbeats.
    if data.health:
        from app.services import metrics_service

        try:
            await metrics_service.ingest_health(session, node.node_id, data.health)
        except Exception:  # noqa: BLE001 - telemetry is best-effort
            logger.warning("metric ingest failed", extra={"event": "metric_ingest_error"})
    return node
