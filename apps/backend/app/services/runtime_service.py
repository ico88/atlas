"""Runtime / deployment / alias registry operations (multi-runtime Fase 1)."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import gateway
from app.models.runtime import ModelAlias, ModelDeployment, Runtime

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Runtimes
# --------------------------------------------------------------------------- #
async def list_runtimes(session: AsyncSession) -> list[Runtime]:
    rows = await session.execute(select(Runtime).order_by(Runtime.name.asc()))
    return list(rows.scalars().all())


async def get_runtime(session: AsyncSession, runtime_id: str) -> Runtime | None:
    return await session.get(Runtime, runtime_id)


async def get_runtime_by_name(session: AsyncSession, name: str) -> Runtime | None:
    return (
        await session.execute(select(Runtime).where(Runtime.name == name))
    ).scalar_one_or_none()


async def create_runtime(session: AsyncSession, **fields) -> Runtime:
    runtime = Runtime(**fields)
    session.add(runtime)
    await session.commit()
    await session.refresh(runtime)
    logger.info(
        "runtime registered",
        extra={
            "event": "runtime_add",
            "context": {"name": runtime.name, "type": runtime.runtime_type},
        },
    )
    return runtime


async def update_runtime(session: AsyncSession, runtime: Runtime, **fields) -> Runtime:
    for key, value in fields.items():
        if value is not None:
            setattr(runtime, key, value)
    await session.commit()
    await session.refresh(runtime)
    return runtime


async def delete_runtime(session: AsyncSession, runtime: Runtime) -> None:
    await session.delete(runtime)
    await session.commit()


async def health_all(session: AsyncSession) -> list[dict]:
    """Probe every runtime and persist its status. Never raises per runtime."""

    out: list[dict] = []
    for runtime in await list_runtimes(session):
        state, detail = "DOWN", "disabled"
        if runtime.enabled:
            try:
                adapter = gateway.adapter_for(runtime)
                health = await adapter.health()
                state, detail = health.state.value, health.detail
            except ValueError as exc:
                state, detail = "DOWN", str(exc)
        runtime.status = state
        out.append(
            {
                "id": runtime.id,
                "name": runtime.name,
                "runtime_type": runtime.runtime_type,
                "state": state,
                "detail": detail,
            }
        )
    await session.commit()
    return out


# --------------------------------------------------------------------------- #
# Deployments
# --------------------------------------------------------------------------- #
async def list_deployments(session: AsyncSession) -> list[ModelDeployment]:
    rows = await session.execute(
        select(ModelDeployment).order_by(ModelDeployment.priority.desc())
    )
    return list(rows.scalars().all())


async def get_deployment(session: AsyncSession, dep_id: str) -> ModelDeployment | None:
    return await session.get(ModelDeployment, dep_id)


async def create_deployment(session: AsyncSession, **fields) -> ModelDeployment:
    dep = ModelDeployment(**fields)
    session.add(dep)
    await session.commit()
    await session.refresh(dep)
    logger.info(
        "model deployment registered",
        extra={
            "event": "deployment_add",
            "context": {"model_key": dep.model_key, "runtime_id": dep.runtime_id},
        },
    )
    return dep


async def update_deployment(
    session: AsyncSession, dep: ModelDeployment, **fields
) -> ModelDeployment:
    for key, value in fields.items():
        if value is not None:
            setattr(dep, key, value)
    await session.commit()
    await session.refresh(dep)
    return dep


async def delete_deployment(session: AsyncSession, dep: ModelDeployment) -> None:
    await session.delete(dep)
    await session.commit()


# --------------------------------------------------------------------------- #
# Aliases
# --------------------------------------------------------------------------- #
async def list_aliases(session: AsyncSession) -> list[ModelAlias]:
    rows = await session.execute(select(ModelAlias).order_by(ModelAlias.alias.asc()))
    return list(rows.scalars().all())


async def upsert_alias(
    session: AsyncSession, *, alias: str, targets: list[str], description: str | None, enabled: bool
) -> ModelAlias:
    row = (
        await session.execute(select(ModelAlias).where(ModelAlias.alias == alias))
    ).scalar_one_or_none()
    if row is None:
        row = ModelAlias(alias=alias)
        session.add(row)
    row.targets = list(targets)
    row.description = description
    row.enabled = enabled
    await session.commit()
    await session.refresh(row)
    return row


async def delete_alias(session: AsyncSession, alias_row: ModelAlias) -> None:
    await session.delete(alias_row)
    await session.commit()
