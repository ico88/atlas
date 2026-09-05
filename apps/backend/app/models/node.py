"""Node model (spec §8, §14: nodes)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, pk_column, utcnow


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[str] = pk_column()
    node_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Version the control plane wants this node on (fleet deployments, PR 21/22).
    # The node agent applies it and reports back via `version` on the next heartbeat.
    desired_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    # Quarantined nodes are excluded from scheduling until reinstated (PR 25).
    quarantined: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    capabilities: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    hardware: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    last_heartbeat: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
