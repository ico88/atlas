"""Node registration, heartbeat and liveness helpers (spec §8)."""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.base import utcnow
from app.models.node import Node
from app.schemas.node import NodeHeartbeat, NodeRegister

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
    return node
