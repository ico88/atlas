"""Provider and Model registry (spec §14: providers, models)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, pk_column, utcnow


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[str] = pk_column()
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="local")
    base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class LLMModel(Base):
    __tablename__ = "models"

    id: Mapped[str] = pk_column()
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    # Stable logical key for aliases/deployments (e.g. "qwen-local-8b-q4"),
    # independent of the runtime-specific ``name``. Nullable for legacy rows.
    model_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parameter_count: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quantization: Mapped[str | None] = mapped_column(String(32), nullable=True)
    format: Mapped[str | None] = mapped_column(String(32), nullable=True)  # GGUF, …
    context_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capabilities: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
