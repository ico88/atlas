"""Continuous Improvement models (ROADMAP PR 18).

An **improvement proposal** captures a change we might adopt (a different default
model, a config tweak, a prompt change), an **experiment** evaluates the candidate
against a baseline on an eval suite (PR 16), the **comparison** decides whether it
is an improvement or a regression, and a human **approval** gates whether it is
actually applied. Nothing is ever applied automatically.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, pk_column, utcnow


class ProposalStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    EXPERIMENTED = "EXPERIMENTED"  # baseline vs candidate compared, awaiting approval
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    APPLIED = "APPLIED"


class ProposalCategory(str, enum.Enum):
    MODEL = "model"
    CONFIG = "config"
    PROMPT = "prompt"


class ImprovementProposal(Base):
    __tablename__ = "improvement_proposals"

    id: Mapped[str] = pk_column()
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ProposalCategory.MODEL.value
    )
    suite_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("eval_suites.id", ondelete="SET NULL"), nullable=True
    )
    baseline_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    candidate_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # What apply() will do, e.g. {"default_model": "llama3.2:3b"}.
    change: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ProposalStatus.DRAFT.value, index=True
    )
    baseline_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    candidate_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    comparison: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # improvement | regression | neutral | inconclusive
    recommendation: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
