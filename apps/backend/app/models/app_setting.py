"""Runtime application settings (ROADMAP PR 15 config UI).

A tiny key/value store for operator-editable settings that override environment
defaults at request time (e.g. enabling web tools and choosing a search provider
from the UI). Values are JSON blobs keyed by a short namespace (e.g. ``web``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
