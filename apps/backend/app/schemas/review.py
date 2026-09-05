"""Critical Review API schemas (ROADMAP PR 19)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReviewRequest(BaseModel):
    prompt: str = Field(min_length=1)
    references: list[str] | None = None  # facts the answer should be grounded in
    max_rounds: int | None = Field(default=None, ge=1, le=8)
    model: str | None = None


class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    prompt: str
    references: list[Any] | None
    best_answer: str | None
    best_score: float
    decision: str
    rounds: list[Any] | None
    consensus: dict[str, Any] | None
    provider: str | None
    model: str | None
    round_count: int
    created_at: datetime


class ReviewSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    prompt: str
    best_score: float
    decision: str
    round_count: int
    created_at: datetime


class ReviewList(BaseModel):
    items: list[ReviewSummary]
    total: int
