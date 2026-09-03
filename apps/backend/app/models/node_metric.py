"""Node resource telemetry (ROADMAP PR 12).

A time-series of health samples ingested from node heartbeats (load, free RAM,
and any extra fields the agent reports). Kept small via a per-node retention cap.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, pk_column, utcnow


class NodeMetric(Base):
    __tablename__ = "node_metrics"

    id: Mapped[str] = pk_column()
    node_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    load1: Mapped[float | None] = mapped_column(Float, nullable=True)
    ram_free_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
