"""Resource telemetry service (ROADMAP PR 12).

Ingests node health samples from heartbeats into a bounded time-series, and
aggregates Ollama performance from the messages already recorded by the chat
layer (latency per provider/model) — no extra writes on the hot path.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.conversation import Message
from app.models.node_metric import NodeMetric

logger = logging.getLogger(__name__)


def _num(value: Any) -> float | None:
    return value if isinstance(value, int | float) and not isinstance(value, bool) else None


async def ingest_health(
    session: AsyncSession, node_id: str, health: dict[str, Any] | None
) -> NodeMetric | None:
    """Persist one telemetry sample from a heartbeat's health payload."""

    if not health:
        return None
    metric = NodeMetric(
        node_id=node_id,
        load1=_num(health.get("load1")),
        ram_free_mb=int(health["ram_free_mb"]) if _num(health.get("ram_free_mb")) else None,
        data=dict(health),
    )
    session.add(metric)
    await session.commit()
    await session.refresh(metric)
    await _prune(session, node_id)
    return metric


async def _prune(session: AsyncSession, node_id: str) -> None:
    """Keep only the most recent ``metrics_history_limit`` samples per node."""

    keep = get_settings().metrics_history_limit
    if keep <= 0:
        return
    ids = list(
        (
            await session.execute(
                select(NodeMetric.id)
                .where(NodeMetric.node_id == node_id)
                .order_by(NodeMetric.created_at.desc())
                .offset(keep)
            )
        )
        .scalars()
        .all()
    )
    if ids:
        await session.execute(delete(NodeMetric).where(NodeMetric.id.in_(ids)))
        await session.commit()


async def history(session: AsyncSession, node_id: str, *, limit: int = 100) -> list[NodeMetric]:
    result = await session.execute(
        select(NodeMetric)
        .where(NodeMetric.node_id == node_id)
        .order_by(NodeMetric.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def latest_per_node(session: AsyncSession) -> list[NodeMetric]:
    """The most recent sample for each node."""

    rows = list(
        (
            await session.execute(
                select(NodeMetric).order_by(NodeMetric.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    seen: dict[str, NodeMetric] = {}
    for m in rows:
        seen.setdefault(m.node_id, m)
    return list(seen.values())


async def ollama_perf(session: AsyncSession) -> list[dict[str, Any]]:
    """Aggregate latency per provider/model from recorded assistant messages."""

    stmt = (
        select(
            Message.provider,
            Message.model,
            func.count().label("n"),
            func.avg(Message.latency_ms).label("avg_latency_ms"),
            func.min(Message.latency_ms).label("min_latency_ms"),
            func.max(Message.latency_ms).label("max_latency_ms"),
        )
        .where(Message.provider.is_not(None), Message.latency_ms.is_not(None))
        .group_by(Message.provider, Message.model)
        .order_by(func.count().desc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "provider": r.provider,
            "model": r.model,
            "count": int(r.n),
            "avg_latency_ms": round(float(r.avg_latency_ms), 1) if r.avg_latency_ms else None,
            "min_latency_ms": int(r.min_latency_ms) if r.min_latency_ms is not None else None,
            "max_latency_ms": int(r.max_latency_ms) if r.max_latency_ms is not None else None,
        }
        for r in rows
    ]
