"""Local fine-tuning pipeline: curation, export, jobs, adoption (self-improvement)."""

from __future__ import annotations

import json

import pytest
from app.models.base import utcnow
from app.models.conversation import Conversation, Message, MessageRole
from app.models.finetune import FineTuneExample, FineTuneJobStatus
from app.models.rag import Feedback
from app.models.task import Task
from app.services import finetune_service


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def test_example_hash_stable_and_trimmed():
    a = finetune_service.example_hash(" hello ", "world ")
    b = finetune_service.example_hash("hello", "world")
    assert a == b
    assert a != finetune_service.example_hash("hello", "worlds")


def test_to_chat_record_shapes():
    rec = finetune_service.to_chat_record("q", "a", "sys")
    assert rec["messages"][0] == {"role": "system", "content": "sys"}
    assert rec["messages"][-1] == {"role": "assistant", "content": "a"}
    assert finetune_service.to_chat_record("q", "a")["messages"][0]["role"] == "user"


def test_build_jsonl_only_included():
    examples = [
        FineTuneExample(
            dataset_id="d", prompt="p1", response="r1", content_hash="h1", included=True
        ),
        FineTuneExample(
            dataset_id="d", prompt="p2", response="r2", content_hash="h2", included=False
        ),
    ]
    out = finetune_service.build_jsonl(examples)
    lines = out.splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["messages"][0]["content"] == "p1"


# --------------------------------------------------------------------------- #
# Curation from feedback
# --------------------------------------------------------------------------- #
async def _rated_exchange(session, user_text: str, reply_text: str, rating: int = 1) -> str:
    convo = Conversation(title="c", mode="auto")
    session.add(convo)
    await session.flush()
    user = Message(conversation_id=convo.id, role=MessageRole.USER.value, content=user_text)
    session.add(user)
    await session.flush()
    reply = Message(
        conversation_id=convo.id, role=MessageRole.ASSISTANT.value, content=reply_text
    )
    session.add(reply)
    await session.flush()
    session.add(Feedback(target_type="message", target_id=reply.id, rating=rating))
    await session.commit()
    return reply.id


@pytest.mark.asyncio
async def test_curate_harvests_positive_feedback_and_dedups(session):
    await _rated_exchange(session, "Ciao", "Ciao! Come posso aiutarti?", rating=1)
    await _rated_exchange(session, "Bad", "meh", rating=-1)  # ignored (negative)
    ds = await finetune_service.create_dataset(session, name="d1")

    added = await finetune_service.curate_from_feedback(session, dataset_id=ds.id)
    assert added == 1
    examples = await finetune_service.list_examples(session, ds.id)
    assert examples[0].source == "feedback"
    assert examples[0].prompt == "Ciao"

    # Re-curating is idempotent (dedup by content hash).
    assert await finetune_service.curate_from_feedback(session, dataset_id=ds.id) == 0


@pytest.mark.asyncio
async def test_add_example_dedups(session):
    ds = await finetune_service.create_dataset(session, name="d2")
    first = await finetune_service.add_example(session, dataset_id=ds.id, prompt="p", response="r")
    assert first is not None
    dup = await finetune_service.add_example(session, dataset_id=ds.id, prompt="p", response="r")
    assert dup is None


# --------------------------------------------------------------------------- #
# Jobs: dispatch, sync, adopt
# --------------------------------------------------------------------------- #
async def _gpu_node(client):
    return await client.post(
        "/api/v1/nodes/register",
        json={"node_id": "trainer-1", "label": "Zotac", "capabilities": {"gpu": True}},
    )


@pytest.mark.asyncio
async def test_create_job_requires_examples(session):
    ds = await finetune_service.create_dataset(session, name="empty")
    with pytest.raises(finetune_service.FineTuneError):
        await finetune_service.create_job(session, dataset_id=ds.id, base_model="llama3.2:3b")


@pytest.mark.asyncio
async def test_job_dispatches_gpu_task_and_syncs_and_adopts(client, session):
    await _gpu_node(client)
    ds = await finetune_service.create_dataset(session, name="prod", base_model="llama3.2:3b")
    await finetune_service.add_example(session, dataset_id=ds.id, prompt="p", response="r")

    job = await finetune_service.create_job(session, dataset_id=ds.id)
    assert job.status == FineTuneJobStatus.QUEUED.value
    assert job.task_id
    assert job.adapter_name.endswith("-ft")

    # The dispatched task requires the GPU capability and carries the training set.
    task = await session.get(Task, job.task_id)
    assert task.type == "fine_tune"
    assert task.required_capability == "gpu"
    assert task.payload["example_count"] == 1

    # Simulate the node finishing the training task.
    task.status = "COMPLETED"
    task.result = {"result": {"model": "llama3.2-prod-ft", "metrics": {"final_loss": 0.2}}}
    task.completed_at = utcnow()
    await session.commit()

    job = await finetune_service.sync_job(session, job)
    assert job.status == FineTuneJobStatus.COMPLETED.value
    assert job.metrics == {"final_loss": 0.2}

    # Adoption routes the adapter through the standard improvement/canary rails.
    proposal = await finetune_service.adopt_job(session, job)
    assert proposal.candidate_model == "llama3.2-prod-ft"
    assert proposal.baseline_model == "llama3.2:3b"


@pytest.mark.asyncio
async def test_sync_job_reflects_failure(client, session):
    await _gpu_node(client)
    ds = await finetune_service.create_dataset(session, name="failing", base_model="m")
    await finetune_service.add_example(session, dataset_id=ds.id, prompt="p", response="r")
    job = await finetune_service.create_job(session, dataset_id=ds.id)

    task = await session.get(Task, job.task_id)
    task.status = "FAILED"
    task.error = "no local training backend"
    task.completed_at = utcnow()
    await session.commit()

    job = await finetune_service.sync_job(session, job)
    assert job.status == FineTuneJobStatus.FAILED.value
    assert "backend" in (job.error or "")


# --------------------------------------------------------------------------- #
# API surface + readiness
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_readiness_and_full_api_flow(client, session):
    # No GPU node yet, no feedback → readiness is honest about the gaps.
    r0 = (await client.get("/api/v1/finetune/readiness")).json()
    assert r0["gpu_node_available"] is False
    assert r0["positive_feedback"] == 0

    await _gpu_node(client)
    await _rated_exchange(session, "Q", "A good answer", rating=1)

    r1 = (await client.get("/api/v1/finetune/readiness")).json()
    assert r1["gpu_node_available"] is True
    assert "Zotac" in r1["gpu_node_names"]
    assert r1["positive_feedback"] == 1

    ds = (await client.post("/api/v1/finetune/datasets", json={"name": "api-ds"})).json()
    curated = (
        await client.post(f"/api/v1/finetune/datasets/{ds['id']}/curate", json={"min_rating": 1})
    ).json()
    assert curated["added"] == 1

    export = await client.get(f"/api/v1/finetune/datasets/{ds['id']}/export")
    assert export.status_code == 200
    assert json.loads(export.text.splitlines()[0])["messages"][0]["content"] == "Q"

    job = (
        await client.post(
            "/api/v1/finetune/jobs",
            json={"dataset_id": ds["id"], "base_model": "llama3.2:3b"},
        )
    ).json()
    assert job["status"] == "QUEUED"

    jobs = (await client.get("/api/v1/finetune/jobs")).json()
    assert jobs["total"] == 1


@pytest.mark.asyncio
async def test_create_job_without_examples_returns_400(client, session):
    ds = (await client.post("/api/v1/finetune/datasets", json={"name": "no-ex"})).json()
    resp = await client.post(
        "/api/v1/finetune/jobs", json={"dataset_id": ds["id"], "base_model": "m"}
    )
    assert resp.status_code == 400
