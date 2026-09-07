"""Service-level objectives, alerts & report (ROADMAP R5).

Turns the metrics ATLAS already collects into a small SLO report: each objective
has a measured value and a target; anything below target becomes an advisory
alert on the Admin page. The scoring is a pure function so it is unit-tested;
``report`` gathers the live inputs.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.base import utcnow
from app.models.task import Task, TaskStatus
from app.services import node_service


def evaluate(
    *,
    completed: int,
    failed: int,
    nodes_total: int,
    nodes_online: int,
    healthy: bool,
    task_target: float,
    nodes_target: float,
) -> dict[str, Any]:
    """Pure: build the SLO list + alerts from raw counts. Higher is better."""

    slos: list[dict[str, Any]] = []

    finished = completed + failed
    if finished > 0:
        success = round(completed / finished, 4)
        slos.append(
            {
                "name": "task_success_rate",
                "value": success,
                "target": task_target,
                "ok": success >= task_target,
                "unit": "ratio",
            }
        )

    if nodes_total > 0:
        online = round(nodes_online / nodes_total, 4)
        slos.append(
            {
                "name": "nodes_online_ratio",
                "value": online,
                "target": nodes_target,
                "ok": online >= nodes_target,
                "unit": "ratio",
            }
        )

    slos.append(
        {"name": "control_plane_healthy", "value": 1.0 if healthy else 0.0,
         "target": 1.0, "ok": healthy, "unit": "bool"}
    )

    alerts = [
        {"slo": s["name"], "value": s["value"], "target": s["target"]}
        for s in slos
        if not s["ok"]
    ]
    return {"slos": slos, "alerts": alerts, "ok": not alerts}


async def report(session: AsyncSession, *, healthy: bool = True) -> dict[str, Any]:
    """Gather live inputs and evaluate the SLOs."""

    settings = get_settings()
    counts = {
        status: int(n)
        for status, n in (
            await session.execute(select(Task.status, func.count()).group_by(Task.status))
        ).all()
    }
    nodes = await node_service.list_nodes(session)
    online = sum(1 for n in nodes if node_service.is_online(n))

    result = evaluate(
        completed=counts.get(TaskStatus.COMPLETED.value, 0),
        failed=counts.get(TaskStatus.FAILED.value, 0),
        nodes_total=len(nodes),
        nodes_online=online,
        healthy=healthy,
        task_target=settings.slo_task_success_target,
        nodes_target=settings.slo_nodes_online_target,
    )
    result["generated_at"] = utcnow().isoformat()
    return result
