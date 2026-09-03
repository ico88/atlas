"""Environment service (ROADMAP PR 13): manifest, isolation, snapshot/restore."""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utcnow
from app.models.environment import Environment, EnvironmentSnapshot, EnvironmentStatus
from app.models.query import Query
from app.models.rag import Memory
from app.models.task import Task

logger = logging.getLogger(__name__)


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "env"


async def _unique_slug(session: AsyncSession, base: str) -> str:
    slug = base
    n = 1
    while (
        await session.execute(select(Environment).where(Environment.slug == slug))
    ).scalar_one_or_none() is not None:
        n += 1
        slug = f"{base}-{n}"
    return slug


async def create_environment(
    session: AsyncSession,
    *,
    name: str,
    description: str | None = None,
    manifest: dict[str, Any] | None = None,
    variables: dict[str, Any] | None = None,
) -> Environment:
    env = Environment(
        name=name,
        slug=await _unique_slug(session, slugify(name)),
        description=description,
        manifest=manifest,
        variables=variables,
        status=EnvironmentStatus.ACTIVE.value,
    )
    session.add(env)
    await session.commit()
    await session.refresh(env)
    logger.info(
        "environment created", extra={"event": "env_created", "context": {"slug": env.slug}}
    )
    return env


async def list_environments(
    session: AsyncSession, *, include_archived: bool = True
) -> list[Environment]:
    stmt = select(Environment).order_by(Environment.created_at.desc())
    if not include_archived:
        stmt = stmt.where(Environment.status == EnvironmentStatus.ACTIVE.value)
    return list((await session.execute(stmt)).scalars().all())


async def get_by_ref(session: AsyncSession, ref: str) -> Environment | None:
    env = await session.get(Environment, ref)
    if env is not None:
        return env
    return (
        await session.execute(select(Environment).where(Environment.slug == ref))
    ).scalar_one_or_none()


async def update_environment(
    session: AsyncSession,
    env: Environment,
    *,
    name: str | None = None,
    description: str | None = None,
    manifest: dict[str, Any] | None = None,
    variables: dict[str, Any] | None = None,
    status: str | None = None,
) -> Environment:
    if name is not None:
        env.name = name
    if description is not None:
        env.description = description
    if manifest is not None:
        env.manifest = manifest
    if variables is not None:
        env.variables = variables
    if status is not None:
        env.status = status
    await session.commit()
    await session.refresh(env)
    return env


async def archive_environment(session: AsyncSession, env: Environment) -> Environment:
    return await update_environment(session, env, status=EnvironmentStatus.ARCHIVED.value)


async def environment_stats(session: AsyncSession, env_id: str) -> dict[str, int]:
    async def _count(model) -> int:
        return int(
            (
                await session.execute(
                    select(func.count()).select_from(model).where(model.environment_id == env_id)
                )
            ).scalar_one()
        )

    return {
        "tasks": await _count(Task),
        "queries": await _count(Query),
        "memories": await _count(Memory),
    }


async def create_snapshot(
    session: AsyncSession,
    env: Environment,
    *,
    name: str | None = None,
    created_by: str | None = None,
) -> EnvironmentSnapshot:
    """Capture the environment's manifest + variables (config) and a stats summary."""

    snapshot = EnvironmentSnapshot(
        environment_id=env.id,
        name=name,
        manifest=env.manifest,
        variables=env.variables,
        stats=await environment_stats(session, env.id),
        created_by=created_by,
    )
    session.add(snapshot)
    await session.commit()
    await session.refresh(snapshot)
    logger.info(
        "environment snapshot", extra={"event": "env_snapshot", "context": {"slug": env.slug}}
    )
    return snapshot


async def list_snapshots(session: AsyncSession, env_id: str) -> list[EnvironmentSnapshot]:
    stmt = (
        select(EnvironmentSnapshot)
        .where(EnvironmentSnapshot.environment_id == env_id)
        .order_by(EnvironmentSnapshot.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_snapshot(session: AsyncSession, snapshot_id: str) -> EnvironmentSnapshot | None:
    return await session.get(EnvironmentSnapshot, snapshot_id)


async def restore_snapshot(
    session: AsyncSession, snapshot: EnvironmentSnapshot
) -> Environment:
    """Restore an environment's manifest + variables from a snapshot (config-level).

    Scoped *data* (tasks/queries/memories) is left as-is by design — restore
    reinstates the declared configuration, not historical run data.
    """

    env = await session.get(Environment, snapshot.environment_id)
    if env is None:
        raise ValueError("environment no longer exists")
    env.manifest = snapshot.manifest
    env.variables = snapshot.variables
    env.updated_at = utcnow()
    await session.commit()
    await session.refresh(env)
    logger.info(
        "environment restored",
        extra={"event": "env_restored", "context": {"slug": env.slug}},
    )
    return env
