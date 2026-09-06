"""Append-only, tamper-evident audit trail (ROADMAP R5).

``record`` appends one hash-chained entry; ``verify_chain`` recomputes the chain
and reports the first break (an edited/deleted/reordered row). There is no update
or delete path — the log is append-only by construction.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog

logger = logging.getLogger(__name__)

GENESIS = "0" * 64


def compute_hash(
    seq: int,
    prev_hash: str,
    actor: str,
    action: str,
    target: str | None,
    detail: dict[str, Any] | None,
    created_at: datetime,
) -> str:
    """Deterministic SHA-256 over the canonical entry representation."""

    # Normalize to naive-UTC so the hash is stable across the DB round-trip
    # (SQLite returns naive datetimes, PostgreSQL tz-aware) and across backends.
    norm = created_at.astimezone(UTC).replace(tzinfo=None) if created_at.tzinfo else created_at
    canonical = "|".join(
        [
            str(seq),
            prev_hash,
            actor,
            action,
            target or "",
            json.dumps(detail or {}, sort_keys=True, ensure_ascii=False),
            norm.isoformat(),
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def record(
    session: AsyncSession,
    *,
    action: str,
    actor: str = "system",
    target: str | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditLog:
    """Append one audit entry, chained to the previous. Never raises to callers'
    critical paths — callers should still wrap it if audit is non-essential."""

    last = (
        await session.execute(select(AuditLog).order_by(AuditLog.seq.desc()).limit(1))
    ).scalar_one_or_none()
    seq = (last.seq + 1) if last else 1
    prev_hash = last.hash if last else GENESIS
    from app.models.base import utcnow

    created_at = utcnow()
    entry = AuditLog(
        seq=seq,
        actor=actor,
        action=action,
        target=target,
        detail=detail,
        prev_hash=prev_hash,
        hash=compute_hash(seq, prev_hash, actor, action, target, detail, created_at),
        created_at=created_at,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def verify_chain(session: AsyncSession) -> dict[str, Any]:
    """Recompute the chain. Returns {ok, count, broken_at?} — broken_at is the seq
    of the first entry whose hash or linkage doesn't match (tampering)."""

    rows = (
        await session.execute(select(AuditLog).order_by(AuditLog.seq.asc()))
    ).scalars().all()
    prev_hash = GENESIS
    for row in rows:
        expected = compute_hash(
            row.seq, prev_hash, row.actor, row.action, row.target, row.detail, row.created_at
        )
        if row.prev_hash != prev_hash or row.hash != expected:
            return {"ok": False, "count": len(rows), "broken_at": row.seq}
        prev_hash = row.hash
    return {"ok": True, "count": len(rows)}


async def list_entries(session: AsyncSession, *, limit: int = 100) -> list[AuditLog]:
    rows = (
        await session.execute(select(AuditLog).order_by(AuditLog.seq.desc()).limit(limit))
    ).scalars().all()
    return list(rows)


async def count(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count(AuditLog.id)))).scalar_one())
