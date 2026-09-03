"""Environment models (ROADMAP PR 13).

An **environment** is a named, isolated workspace: a declarative *manifest*
(models/capabilities/knowledge-bases the environment expects) plus *variables*,
against which tasks, queries and memories can be scoped. A **snapshot** captures
the environment's manifest + variables so it can be restored later.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, pk_column, utcnow


class EnvironmentStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class Environment(Base):
    __tablename__ = "environments"

    id: Mapped[str] = pk_column()
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=EnvironmentStatus.ACTIVE.value, index=True
    )
    manifest: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    variables: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    snapshots: Mapped[list[EnvironmentSnapshot]] = relationship(
        back_populates="environment",
        cascade="all, delete-orphan",
        order_by="EnvironmentSnapshot.created_at.desc()",
    )


class EnvironmentSnapshot(Base):
    __tablename__ = "environment_snapshots"

    id: Mapped[str] = pk_column()
    environment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("environments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    manifest: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    variables: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # A small, non-authoritative summary of scoped state at capture time.
    stats: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    environment: Mapped[Environment] = relationship(back_populates="snapshots")
