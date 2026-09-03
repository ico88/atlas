"""Evaluation models (ROADMAP PR 16).

A small, offline-friendly eval harness: a **suite** holds **cases** (input +
expected/forbidden substrings + category); a **run** executes the suite against a
provider/model and stores per-case **results** and aggregate quality / safety /
performance metrics.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, pk_column, utcnow


class EvalRunStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EvalSuite(Base):
    __tablename__ = "eval_suites"

    id: Mapped[str] = pk_column()
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    cases: Mapped[list[EvalCase]] = relationship(
        back_populates="suite", cascade="all, delete-orphan", order_by="EvalCase.created_at"
    )


class EvalCase(Base):
    __tablename__ = "eval_cases"

    id: Mapped[str] = pk_column()
    suite_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("eval_suites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    input: Mapped[str] = mapped_column(Text, nullable=False)
    expected_substrings: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    forbidden_substrings: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="quality")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    suite: Mapped[EvalSuite] = relationship(back_populates="cases")


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[str] = pk_column()
    suite_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("eval_suites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=EvalRunStatus.PENDING.value, index=True
    )
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    is_baseline: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    results: Mapped[list[EvalResult]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="EvalResult.created_at"
    )


class EvalResult(Base):
    __tablename__ = "eval_results"

    id: Mapped[str] = pk_column()
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("eval_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_id: Mapped[str] = mapped_column(String(36), nullable=False)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quality: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    safety: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    run: Mapped[EvalRun] = relationship(back_populates="results")
