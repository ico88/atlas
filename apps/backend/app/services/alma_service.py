"""ALMA orchestrator (spec §6, §7, milestone M5).

ALMA takes a high-level objective (a task of type ``alma``) and:

1. **decomposes** it into a DAG of subtasks (with dependencies),
2. lets the existing task engine (M3) run them — independent subtasks in
   parallel, each with its own retry/backoff,
3. **aggregates** the subtask results back into the parent when they all
   complete, and propagates a subtask failure to the parent.

It reuses the M3 dependency machinery: the ALMA task itself depends on all its
subtasks, so it is automatically re-queued (for the aggregation phase) once the
last subtask completes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task, TaskDependency, TaskStatus
from app.schemas.task import TaskCreate
from app.services import queue, task_service

logger = logging.getLogger(__name__)

ALMA_TASK_TYPE = "alma"


@dataclass
class PlanStep:
    key: str
    title: str
    type: str = "dummy"
    payload: dict | None = None
    depends_on: list[str] = field(default_factory=list)


def build_plan(alma: Task) -> list[PlanStep]:
    """Produce a subtask DAG for the objective.

    If ``payload.plan`` is provided it is used verbatim (deterministic, and how
    ALMA will later consume an LLM-produced plan). Otherwise a default linear
    Analyze -> Execute -> Summarize plan is generated.
    """

    payload = alma.payload or {}
    objective = alma.objective or alma.title or "objective"

    explicit = payload.get("plan")
    if isinstance(explicit, list) and explicit:
        steps: list[PlanStep] = []
        for i, item in enumerate(explicit):
            steps.append(
                PlanStep(
                    key=str(item.get("key", f"s{i}")),
                    title=str(item.get("title", f"Step {i + 1}")),
                    type=str(item.get("type", "dummy")),
                    payload=item.get("payload"),
                    depends_on=[str(k) for k in item.get("depends_on", [])],
                )
            )
        return steps

    return [
        PlanStep("analyze", f"Analyze: {objective}", payload={"phase": "analyze"}),
        PlanStep(
            "execute",
            f"Execute: {objective}",
            payload={"phase": "execute"},
            depends_on=["analyze"],
        ),
        PlanStep(
            "summarize",
            f"Summarize: {objective}",
            payload={"phase": "summarize"},
            depends_on=["execute"],
        ),
    ]


async def get_children(session: AsyncSession, alma_id: str) -> list[Task]:
    result = await session.execute(
        select(Task).where(Task.parent_task_id == alma_id).order_by(Task.created_at.asc())
    )
    return list(result.scalars().all())


async def decompose(session: AsyncSession, alma: Task) -> list[Task]:
    """Create the subtask DAG and move ALMA into WAITING_DEPENDENCY."""

    plan = build_plan(alma)
    key_to_id: dict[str, str] = {}
    created: list[Task] = []

    for step in plan:
        dep_ids = [key_to_id[k] for k in step.depends_on if k in key_to_id]
        sub = await task_service.create_task(
            session,
            TaskCreate(
                title=step.title,
                type=step.type,
                payload=step.payload,
                parent_task_id=alma.id,
                correlation_id=alma.correlation_id,  # propagate correlation (§12)
                depends_on=dep_ids or None,
            ),
        )
        key_to_id[step.key] = sub.id
        created.append(sub)

    # The ALMA task depends on every subtask, so it is re-queued only once they
    # have all completed (aggregation phase).
    for sub in created:
        session.add(TaskDependency(task_id=alma.id, depends_on_task_id=sub.id))
    alma.status = TaskStatus.WAITING_DEPENDENCY.value
    await task_service.record_event(
        session,
        alma,
        "planned",
        status=TaskStatus.WAITING_DEPENDENCY,
        message=f"Decomposed into {len(created)} subtasks",
        data={"subtask_ids": [s.id for s in created]},
    )
    await session.commit()

    # Enqueue the subtasks that are immediately runnable (no dependencies).
    for sub in created:
        await session.refresh(sub)
        if sub.status == TaskStatus.QUEUED.value:
            await queue.enqueue(sub.id)

    logger.info(
        "alma decomposed objective",
        extra={"event": "alma_decomposed", "context": {"alma_id": alma.id, "n": len(created)}},
    )
    return created


async def aggregate(session: AsyncSession, alma: Task) -> Task:
    """Combine subtask results into the ALMA task and complete it."""

    children = await get_children(session, alma.id)
    subtasks = [
        {"id": c.id, "title": c.title, "status": c.status, "result": c.result}
        for c in children
    ]
    aggregated = {
        "objective": alma.objective or alma.title,
        "subtask_count": len(children),
        "completed": sum(1 for c in children if c.status == TaskStatus.COMPLETED.value),
        "subtasks": subtasks,
    }
    await task_service.mark_completed(session, alma, result=aggregated)
    logger.info(
        "alma aggregated results",
        extra={"event": "alma_aggregated", "context": {"alma_id": alma.id}},
    )
    return alma


async def step(session: AsyncSession, alma: Task) -> None:
    """One ALMA turn: decompose if new, otherwise aggregate when children done."""

    children = await get_children(session, alma.id)
    if not children:
        await decompose(session, alma)
        return
    if all(c.status == TaskStatus.COMPLETED.value for c in children):
        await aggregate(session, alma)
        return
    # Re-queued prematurely (shouldn't normally happen) -> keep waiting.
    alma.status = TaskStatus.WAITING_DEPENDENCY.value
    await session.commit()


async def on_subtask_failed(session: AsyncSession, subtask: Task) -> None:
    """Propagate a subtask's terminal failure to its ALMA parent."""

    if not subtask.parent_task_id:
        return
    parent = await session.get(Task, subtask.parent_task_id)
    if parent is None or parent.type != ALMA_TASK_TYPE:
        return
    if TaskStatus(parent.status).is_terminal:
        return
    await task_service.mark_failed(
        session, parent, error=f"subtask {subtask.id} failed: {subtask.error}"
    )
    logger.warning(
        "alma failed due to subtask",
        extra={"event": "alma_failed", "context": {"alma_id": parent.id}},
    )
