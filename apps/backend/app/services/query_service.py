"""Query lifecycle service (ROADMAP PR 10): persist, run, cancel, recover.

A query is created PENDING, executed in the background (owning its own DB
session, like the chat streamer), and driven to a terminal state. Cancellation
is cooperative: a fast Redis flag is checked before each token so a running
query stops promptly and still saves its partial result. Recovery re-queues any
query left RUNNING by a crashed backend.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import redis_client
from app.ai import router
from app.ai.base import ChatMessage
from app.db import get_sessionmaker
from app.models.base import utcnow
from app.models.query import Query, QueryEvent, QueryStatus

logger = logging.getLogger(__name__)

_CANCEL_PREFIX = "atlas:query:cancel:"
_CANCEL_TTL = 3600  # seconds; the DB flag is the durable source of truth


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
async def _record(
    session: AsyncSession, query: Query, event_type: str, *, message: str | None = None
) -> None:
    session.add(
        QueryEvent(
            query_id=query.id,
            event_type=event_type,
            status=query.status,
            message=message,
        )
    )


async def _cancel_flag_set(query_id: str) -> None:
    redis = redis_client.get_redis()
    await cast(Awaitable[bool], redis.set(f"{_CANCEL_PREFIX}{query_id}", "1", ex=_CANCEL_TTL))


async def _cancel_flag_get(query_id: str) -> bool:
    redis = redis_client.get_redis()
    return bool(await cast(Awaitable[object], redis.get(f"{_CANCEL_PREFIX}{query_id}")))


async def _cancel_flag_clear(query_id: str) -> None:
    redis = redis_client.get_redis()
    await cast(Awaitable[int], redis.delete(f"{_CANCEL_PREFIX}{query_id}"))


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #
async def create_query(
    session: AsyncSession,
    *,
    prompt: str,
    mode: str = "AUTO",
    model: str | None = None,
    conversation_id: str | None = None,
    environment_id: str | None = None,
    owner_id: str | None = None,
) -> Query:
    query = Query(
        prompt=prompt,
        mode=mode,
        model=model,
        conversation_id=conversation_id,
        environment_id=environment_id,
        owner_id=owner_id,
        status=QueryStatus.PENDING.value,
    )
    session.add(query)
    await session.flush()
    await _record(session, query, "created")
    await session.commit()
    await session.refresh(query)
    return query


async def get_query(session: AsyncSession, query_id: str) -> Query | None:
    return await session.get(Query, query_id)


async def get_query_with_events(session: AsyncSession, query_id: str) -> Query | None:
    result = await session.execute(
        select(Query).where(Query.id == query_id).options(selectinload(Query.events))
    )
    return result.scalar_one_or_none()


async def list_queries(
    session: AsyncSession,
    *,
    status: str | None = None,
    environment_id: str | None = None,
    limit: int = 100,
) -> tuple[list[Query], int]:
    stmt = select(Query).order_by(Query.created_at.desc())
    count_stmt = select(func.count()).select_from(Query)
    if status:
        stmt = stmt.where(Query.status == status)
        count_stmt = count_stmt.where(Query.status == status)
    if environment_id:
        stmt = stmt.where(Query.environment_id == environment_id)
        count_stmt = count_stmt.where(Query.environment_id == environment_id)
    items = list((await session.execute(stmt.limit(limit))).scalars().all())
    total = int((await session.execute(count_stmt)).scalar_one())
    return items, total


async def request_cancel(session: AsyncSession, query_id: str) -> Query | None:
    """Flag a query for cancellation. Terminal queries are returned unchanged."""

    query = await session.get(Query, query_id)
    if query is None:
        return None
    if QueryStatus(query.status).is_terminal:
        return query
    query.cancel_requested = True
    await _cancel_flag_set(query_id)
    if query.status == QueryStatus.PENDING.value:
        # Not started yet -> cancel immediately.
        query.status = QueryStatus.CANCELLED.value
        query.completed_at = utcnow()
        await _record(session, query, "cancelled", message="cancelled before start")
    else:
        await _record(session, query, "cancel_requested")
    await session.commit()
    await session.refresh(query)
    return query


# --------------------------------------------------------------------------- #
# execution
# --------------------------------------------------------------------------- #
async def run_query(query_id: str, *, heartbeat_every: int = 8) -> None:
    """Execute a query in the background. Owns its own session (post-response)."""

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        query = await session.get(Query, query_id)
        if query is None:
            logger.warning("run_query: %s not found", query_id)
            return
        if QueryStatus(query.status).is_terminal:
            return
        if query.cancel_requested or await _cancel_flag_get(query_id):
            query.status = QueryStatus.CANCELLED.value
            query.completed_at = utcnow()
            await _record(session, query, "cancelled", message="cancelled before start")
            await session.commit()
            return

        # Transition to RUNNING.
        query.status = QueryStatus.RUNNING.value
        query.started_at = utcnow()
        query.heartbeat_at = utcnow()
        await _record(session, query, "started")
        await session.commit()

        decision = await router.select(mode=query.mode, requested_model=query.model)
        query.provider = decision.provider.name
        query.model = decision.model
        await session.commit()

        history = [ChatMessage(role="user", content=query.prompt)]
        parts: list[str] = []
        cancelled = False
        try:
            n = 0
            async for piece in decision.provider.stream_chat(history, decision.model):
                if await _cancel_flag_get(query_id):
                    cancelled = True
                    break
                parts.append(piece)
                n += 1
                if n % heartbeat_every == 0:
                    query.progress = n
                    query.heartbeat_at = utcnow()
                    query.result = "".join(parts)
                    await session.commit()
        except Exception as exc:  # noqa: BLE001 - persist failure, never crash the worker
            logger.exception("query %s failed", query_id)
            query.status = QueryStatus.FAILED.value
            query.error = str(exc)
            query.result = "".join(parts) or None
            query.completed_at = utcnow()
            await _record(session, query, "failed", message=str(exc))
            await session.commit()
            return

        query.result = "".join(parts)
        query.progress = len(parts)
        query.completed_at = utcnow()
        if cancelled:
            query.status = QueryStatus.CANCELLED.value
            await _record(session, query, "cancelled", message="cancelled during run")
        else:
            query.status = QueryStatus.COMPLETED.value
            await _record(session, query, "completed")
        await session.commit()
        await _cancel_flag_clear(query_id)


def schedule_run(query_id: str) -> None:
    """Fire-and-forget background execution (used by the API handler)."""

    asyncio.create_task(run_query(query_id))  # noqa: RUF006 - lifecycle owned by the query row


# --------------------------------------------------------------------------- #
# recovery
# --------------------------------------------------------------------------- #
async def recover_stale(session: AsyncSession, *, stale_after_seconds: float = 0.0) -> list[str]:
    """Re-queue queries left RUNNING by a crashed backend. Returns their ids.

    ``stale_after_seconds`` == 0 recovers *all* RUNNING queries (used at startup,
    where any RUNNING row is necessarily orphaned). A positive value only
    recovers rows whose heartbeat is older than the threshold.
    """

    stmt = select(Query).where(Query.status == QueryStatus.RUNNING.value)
    running = list((await session.execute(stmt)).scalars().all())
    now = time.time()
    recovered: list[str] = []
    for query in running:
        if stale_after_seconds > 0 and query.heartbeat_at is not None:
            age = now - query.heartbeat_at.timestamp()
            if age < stale_after_seconds:
                continue
        query.status = QueryStatus.PENDING.value
        query.started_at = None
        query.heartbeat_at = None
        await _record(session, query, "recovered", message="re-queued after restart")
        recovered.append(query.id)
    if recovered:
        await session.commit()
    return recovered


async def recover_and_resume(*, stale_after_seconds: float = 0.0) -> list[str]:
    """Recover stale queries and schedule them for re-execution (startup hook)."""

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        recovered = await recover_stale(session, stale_after_seconds=stale_after_seconds)
    for query_id in recovered:
        schedule_run(query_id)
    if recovered:
        logger.info(
            "recovered %d stale queries",
            len(recovered),
            extra={"event": "query_recovered"},
        )
    return recovered
