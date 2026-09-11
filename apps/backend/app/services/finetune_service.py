"""Local fine-tuning pipeline (ROADMAP: self-improvement / fine-tuning).

Turns ATLAS's own good interactions into a better model, locally and under the
same guardrails as every other change:

1. **curate** — harvest positively-rated chat replies into a dataset of
   ``prompt -> response`` examples (plus manual add / include-exclude);
2. **export** — render the included examples as chat-format JSONL, the training
   set (pure, unit-tested);
3. **train** — dispatch a ``fine_tune`` task to a GPU-capable node that trains a
   LoRA adapter for a base model (the control plane never trains);
4. **adopt** — hand the finished adapter to the existing improvement → eval →
   canary flow, so a fine-tuned model must still beat the baseline on evals and
   survive the health gate before it can become the default.

Everything here except the training step itself is hardware-independent.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Message, MessageRole
from app.models.finetune import (
    FineTuneDataset,
    FineTuneExample,
    FineTuneJob,
    FineTuneJobStatus,
)
from app.models.rag import Feedback
from app.models.task import Task, TaskStatus
from app.schemas.task import TaskCreate
from app.services import node_service, settings_service, task_service

logger = logging.getLogger(__name__)

# Nodes advertise this capability when they can run a training backend on a GPU.
TRAIN_CAPABILITY = "gpu"


class FineTuneError(RuntimeError):
    pass


# --- pure helpers -----------------------------------------------------------


def example_hash(prompt: str, response: str) -> str:
    """Stable content hash for dedup (prompt+response only)."""

    h = hashlib.sha256()
    h.update(prompt.strip().encode("utf-8"))
    h.update(b"\x00")
    h.update(response.strip().encode("utf-8"))
    return h.hexdigest()


def to_chat_record(
    prompt: str, response: str, system_prompt: str | None = None
) -> dict[str, Any]:
    """One training record in the widely-supported chat JSONL shape."""

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    messages.append({"role": "assistant", "content": response})
    return {"messages": messages}


def build_jsonl(examples: list[FineTuneExample]) -> str:
    """Render included examples as chat-format JSONL (one record per line)."""

    lines = [
        json.dumps(
            to_chat_record(e.prompt, e.response, e.system_prompt), ensure_ascii=False
        )
        for e in examples
        if e.included
    ]
    return "\n".join(lines)


# --- datasets ---------------------------------------------------------------


async def create_dataset(
    session: AsyncSession,
    *,
    name: str,
    description: str | None = None,
    base_model: str | None = None,
) -> FineTuneDataset:
    ds = FineTuneDataset(name=name, description=description, base_model=base_model)
    session.add(ds)
    await session.commit()
    await session.refresh(ds)
    return ds


async def list_datasets(session: AsyncSession) -> list[FineTuneDataset]:
    q = select(FineTuneDataset).order_by(FineTuneDataset.created_at.desc())
    return list((await session.execute(q)).scalars().all())


async def get_dataset(session: AsyncSession, dataset_id: str) -> FineTuneDataset | None:
    return await session.get(FineTuneDataset, dataset_id)


async def delete_dataset(session: AsyncSession, dataset: FineTuneDataset) -> None:
    await session.delete(dataset)
    await session.commit()


async def list_examples(session: AsyncSession, dataset_id: str) -> list[FineTuneExample]:
    q = (
        select(FineTuneExample)
        .where(FineTuneExample.dataset_id == dataset_id)
        .order_by(FineTuneExample.created_at)
    )
    return list((await session.execute(q)).scalars().all())


async def _existing_hashes(session: AsyncSession, dataset_id: str) -> set[str]:
    q = select(FineTuneExample.content_hash).where(
        FineTuneExample.dataset_id == dataset_id
    )
    return set((await session.execute(q)).scalars().all())


async def add_example(
    session: AsyncSession,
    *,
    dataset_id: str,
    prompt: str,
    response: str,
    system_prompt: str | None = None,
    source: str = "manual",
    source_id: str | None = None,
    quality: float = 1.0,
) -> FineTuneExample | None:
    """Add one example; returns None if it duplicates an existing one."""

    ch = example_hash(prompt, response)
    if ch in await _existing_hashes(session, dataset_id):
        return None
    ex = FineTuneExample(
        dataset_id=dataset_id,
        prompt=prompt,
        response=response,
        system_prompt=system_prompt,
        content_hash=ch,
        source=source,
        source_id=source_id,
        quality=quality,
    )
    session.add(ex)
    await session.commit()
    await session.refresh(ex)
    return ex


async def set_example_included(
    session: AsyncSession, example: FineTuneExample, included: bool
) -> FineTuneExample:
    example.included = included
    await session.commit()
    await session.refresh(example)
    return example


async def curate_from_feedback(
    session: AsyncSession, *, dataset_id: str, min_rating: int = 1
) -> int:
    """Harvest positively-rated assistant replies into the dataset.

    For each ``message`` feedback with ``rating >= min_rating`` we take the
    rated assistant reply and the user turn immediately before it in the same
    conversation as one ``prompt -> response`` example. Duplicates (by content
    hash) are skipped. Returns the number of new examples added.
    """

    q = (
        select(Feedback)
        .where(Feedback.target_type == "message", Feedback.rating >= min_rating)
        .order_by(Feedback.created_at)
    )
    feedbacks = list((await session.execute(q)).scalars().all())
    existing = await _existing_hashes(session, dataset_id)
    added = 0
    for fb in feedbacks:
        reply = await session.get(Message, fb.target_id)
        if reply is None or reply.role != MessageRole.ASSISTANT.value:
            continue
        if not (reply.content or "").strip():
            continue
        prompt = await _preceding_user_prompt(session, reply)
        if prompt is None:
            continue
        ch = example_hash(prompt, reply.content)
        if ch in existing:
            continue
        existing.add(ch)
        session.add(
            FineTuneExample(
                dataset_id=dataset_id,
                prompt=prompt,
                response=reply.content,
                content_hash=ch,
                source="feedback",
                source_id=reply.id,
                quality=1.0 + max(0, fb.rating - 1) * 0.1,
            )
        )
        added += 1
    if added:
        await session.commit()
    return added


async def _preceding_user_prompt(session: AsyncSession, reply: Message) -> str | None:
    """The last user message before ``reply`` in its conversation."""

    q = (
        select(Message)
        .where(
            Message.conversation_id == reply.conversation_id,
            Message.role == MessageRole.USER.value,
            Message.created_at <= reply.created_at,
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    msg = (await session.execute(q)).scalars().first()
    if msg is None or not (msg.content or "").strip():
        return None
    return msg.content


# --- readiness --------------------------------------------------------------


async def readiness(session: AsyncSession) -> dict[str, Any]:
    """Honest pre-flight: is a GPU trainer available, and is there enough data?

    Fine-tuning needs (a) an online node advertising a GPU/training backend and
    (b) a non-trivial number of curated examples. This surfaces both so the UI
    can guide instead of failing opaquely.
    """

    nodes = await node_service.list_nodes(session)
    gpu_nodes = [
        n
        for n in nodes
        if node_service.is_online(n) and TRAIN_CAPABILITY in node_service.node_capabilities(n)
    ]
    fb_count = len(
        (
            await session.execute(
                select(Feedback.id).where(
                    Feedback.target_type == "message", Feedback.rating >= 1
                )
            )
        ).scalars().all()
    )
    return {
        "gpu_node_available": bool(gpu_nodes),
        "gpu_node_names": [n.label or n.node_id for n in gpu_nodes],
        "positive_feedback": fb_count,
        # A soft floor; below this a LoRA rarely learns anything useful.
        "recommended_min_examples": 20,
    }


# --- jobs -------------------------------------------------------------------


async def list_jobs(session: AsyncSession, *, dataset_id: str | None = None) -> list[FineTuneJob]:
    q = select(FineTuneJob).order_by(FineTuneJob.created_at.desc())
    if dataset_id:
        q = q.where(FineTuneJob.dataset_id == dataset_id)
    return list((await session.execute(q)).scalars().all())


async def get_job(session: AsyncSession, job_id: str) -> FineTuneJob | None:
    return await session.get(FineTuneJob, job_id)


async def create_job(
    session: AsyncSession,
    *,
    dataset_id: str,
    base_model: str | None = None,
    adapter_name: str | None = None,
    hyperparams: dict[str, Any] | None = None,
) -> FineTuneJob:
    """Snapshot the dataset and dispatch a training task to a GPU node."""

    dataset = await get_dataset(session, dataset_id)
    if dataset is None:
        raise FineTuneError("Dataset not found")
    examples = await list_examples(session, dataset_id)
    training = build_jsonl(examples)
    count = sum(1 for e in examples if e.included)
    if count == 0:
        raise FineTuneError("Dataset has no included examples to train on")

    if not base_model:
        effective = await settings_service.get_effective_settings(session)
        base_model = dataset.base_model or effective.default_model or ""
    if not base_model:
        raise FineTuneError("No base model to fine-tune (set one on the job or a default)")
    if not adapter_name:
        safe = "".join(c if c.isalnum() or c in "-." else "-" for c in dataset.name).strip("-")
        adapter_name = f"{base_model.split(':')[0]}-{safe}-ft"

    job = FineTuneJob(
        dataset_id=dataset_id,
        base_model=base_model,
        adapter_name=adapter_name,
        method="lora",
        example_count=count,
        hyperparams=hyperparams,
        status=FineTuneJobStatus.PENDING.value,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    task = await task_service.create_task(
        session,
        TaskCreate(
            title=f"Fine-tune {adapter_name}",
            type="fine_tune",
            required_capability=TRAIN_CAPABILITY,
            payload={
                "base_model": base_model,
                "adapter_name": adapter_name,
                "method": "lora",
                "hyperparams": hyperparams or {},
                "training_data": training,
                "example_count": count,
            },
        ),
    )
    job.task_id = task.id
    job.status = FineTuneJobStatus.QUEUED.value
    await session.commit()
    await session.refresh(job)
    logger.info(
        "fine-tune job dispatched",
        extra={
            "event": "finetune_dispatch",
            "context": {"job_id": job.id, "task_id": task.id, "examples": count},
        },
    )
    return job


_TASK_TO_JOB = {
    TaskStatus.QUEUED.value: FineTuneJobStatus.QUEUED.value,
    TaskStatus.WAITING_DEPENDENCY.value: FineTuneJobStatus.QUEUED.value,
    TaskStatus.RUNNING.value: FineTuneJobStatus.RUNNING.value,
    TaskStatus.RETRYING.value: FineTuneJobStatus.RUNNING.value,
    TaskStatus.COMPLETED.value: FineTuneJobStatus.COMPLETED.value,
    TaskStatus.FAILED.value: FineTuneJobStatus.FAILED.value,
    TaskStatus.CANCELLED.value: FineTuneJobStatus.CANCELLED.value,
}


async def sync_job(session: AsyncSession, job: FineTuneJob) -> FineTuneJob:
    """Reflect the dispatched training task's state into the job."""

    if not job.task_id or FineTuneJobStatus(job.status).is_terminal:
        return job
    task = await session.get(Task, job.task_id)
    if task is None:
        return job
    new_status = _TASK_TO_JOB.get(task.status, job.status)
    if new_status != job.status:
        job.status = new_status
        if new_status == FineTuneJobStatus.COMPLETED.value:
            result = task.result or {}
            job.output = result.get("result") if isinstance(result, dict) else None
            job.metrics = (job.output or {}).get("metrics") if job.output else None
            job.completed_at = task.completed_at
        elif new_status == FineTuneJobStatus.FAILED.value:
            job.error = task.error
            job.completed_at = task.completed_at
        await session.commit()
        await session.refresh(job)
    return job


async def adopt_job(session: AsyncSession, job: FineTuneJob) -> Any:
    """Route a finished adapter through the standard improvement/canary rails.

    Rather than silently swapping the default, a completed fine-tune becomes an
    improvement proposal whose candidate is the adapter model — so it must beat
    the current default on an eval suite and pass the canary health gate before
    it is ever adopted. Returns the created proposal.
    """

    from app.services import improvement_service

    if job.status != FineTuneJobStatus.COMPLETED.value:
        raise FineTuneError("Only a completed fine-tune can be adopted")
    model_tag = (job.output or {}).get("model") or job.adapter_name
    return await improvement_service.create_proposal(
        session,
        title=f"Adopt fine-tuned {model_tag}",
        description=(
            f"Fine-tuned adapter trained on dataset {job.dataset_id} "
            f"({job.example_count} examples) from base {job.base_model}."
        ),
        baseline_model=job.base_model,
        candidate_model=model_tag,
    )
