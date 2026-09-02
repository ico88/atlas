"""Query lifecycle models (ROADMAP PR 10).

A ``Query`` is a persisted, background-executed AI request. Unlike the ephemeral
``/chat/stream`` turn, a query survives a restart: it is stored, run in the
background, can be **cancelled** cooperatively, and **recovered** (stale RUNNING
queries are re-queued) when the backend starts.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import Base, new_uuid, pk_column, utcnow


class QueryStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        return self in {QueryStatus.COMPLETED, QueryStatus.FAILED, QueryStatus.CANCELLED}


class Query(Base):
    __tablename__ = "queries"

    id: Mapped[str] = pk_column()
    owner_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="AUTO")
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=QueryStatus.PENDING.value, index=True
    )
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # tokens emitted
    correlation_id: Mapped[str] = mapped_column(
        String(36), nullable=False, default=new_uuid, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Liveness marker: refreshed while streaming so recovery can spot a query
    # abandoned by a crashed backend.
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    events: Mapped[list[QueryEvent]] = relationship(
        back_populates="query",
        cascade="all, delete-orphan",
        order_by="QueryEvent.created_at",
    )


class QueryEvent(Base):
    __tablename__ = "query_events"

    id: Mapped[str] = pk_column()
    query_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("queries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    query: Mapped[Query] = relationship(back_populates="events")
