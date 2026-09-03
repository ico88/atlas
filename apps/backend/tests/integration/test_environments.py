"""Environment tests (ROADMAP PR 13): CRUD, manifest, isolation, snapshot/restore."""

from __future__ import annotations

import pytest
from app.schemas.task import TaskCreate
from app.services import environment_service, memory_service, task_service


@pytest.mark.asyncio
async def test_create_slugifies_and_is_unique(session):
    a = await environment_service.create_environment(session, name="My Env!")
    b = await environment_service.create_environment(session, name="My Env!")
    assert a.slug == "my-env"
    assert b.slug == "my-env-2"  # collision resolved


@pytest.mark.asyncio
async def test_snapshot_and_restore_roundtrip(session):
    env = await environment_service.create_environment(
        session, name="prod", manifest={"default_model": "llama3.2"}, variables={"k": "v1"}
    )
    snap = await environment_service.create_snapshot(session, env, name="baseline")
    assert snap.manifest == {"default_model": "llama3.2"}
    assert snap.variables == {"k": "v1"}

    # Drift the environment, then restore the snapshot.
    await environment_service.update_environment(
        session, env, manifest={"default_model": "other"}, variables={"k": "v2"}
    )
    await session.refresh(env)
    assert env.variables == {"k": "v2"}

    restored = await environment_service.restore_snapshot(session, snap)
    assert restored.manifest == {"default_model": "llama3.2"}
    assert restored.variables == {"k": "v1"}


@pytest.mark.asyncio
async def test_stats_and_isolation(session):
    env = await environment_service.create_environment(session, name="iso")
    other = await environment_service.create_environment(session, name="other")

    await task_service.create_task(session, TaskCreate(title="a", environment_id=env.id))
    await task_service.create_task(session, TaskCreate(title="b", environment_id=env.id))
    await task_service.create_task(session, TaskCreate(title="c", environment_id=other.id))
    await memory_service.add_memory(session, content="remember", environment_id=env.id)

    stats = await environment_service.environment_stats(session, env.id)
    assert stats["tasks"] == 2
    assert stats["memories"] == 1

    scoped, total = await task_service.list_tasks(session, environment_id=env.id)
    assert total == 2
    assert all(t.environment_id == env.id for t in scoped)

    mems = await memory_service.list_memories(session, environment_id=env.id)
    assert len(mems) == 1


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_environment_api_flow(client):
    created = await client.post(
        "/api/v1/environments",
        json={"name": "Staging", "manifest": {"cap": ["build"]}, "variables": {"x": 1}},
    )
    assert created.status_code == 201
    env = created.json()
    assert env["slug"] == "staging"

    # Fetch by slug.
    got = await client.get(f"/api/v1/environments/{env['slug']}")
    assert got.status_code == 200

    # Snapshot, then drift, then restore.
    snap = await client.post(f"/api/v1/environments/{env['id']}/snapshots", json={"name": "s1"})
    assert snap.status_code == 201
    snap_id = snap.json()["id"]
    assert snap.json()["stats"]["tasks"] == 0

    await client.patch(f"/api/v1/environments/{env['id']}", json={"variables": {"x": 999}})
    restored = await client.post(f"/api/v1/environments/snapshots/{snap_id}/restore")
    assert restored.status_code == 200
    assert restored.json()["variables"] == {"x": 1}

    listing = await client.get("/api/v1/environments")
    assert listing.json()["total"] >= 1


@pytest.mark.asyncio
async def test_get_unknown_environment_404(client):
    resp = await client.get("/api/v1/environments/nope")
    assert resp.status_code == 404
