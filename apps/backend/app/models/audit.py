"""Append-only audit log (ROADMAP R5 — governance).

A tamper-evident record of sensitive actions. Each entry is chained to the
previous one by a SHA-256 hash (``hash = H(seq | prev_hash | actor | action |
target | detail | created_at)``), so any later edit or deletion breaks the chain
and is detectable via :func:`audit_service.verify_chain`. Entries are only ever
appended — there is no update/delete path in the service or API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, pk_column, utcnow


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = pk_column()
    seq: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="system")
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
