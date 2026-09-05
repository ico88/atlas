"""Critical Review models (ROADMAP PR 19).

A review runs a multi-role pipeline over a prompt — proposer (candidate answer),
critic (finds flaws), verifier (checks claims against references), judge (scores
and decides) — across one or more rounds, then picks the best by adaptive
consensus. The run is persisted for audit.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, pk_column, utcnow


class ReviewDecision(str, enum.Enum):
    ACCEPT = "accept"
    REVISE = "revise"
    REJECT = "reject"


class CriticalReview(Base):
    __tablename__ = "critical_reviews"

    id: Mapped[str] = pk_column()
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    references: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    best_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    best_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    decision: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ReviewDecision.REJECT.value
    )
    rounds: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    consensus: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    round_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
