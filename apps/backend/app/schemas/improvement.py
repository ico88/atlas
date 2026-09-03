"""Continuous Improvement API schemas (ROADMAP PR 18)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProposalCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    category: str = "model"
    suite_id: str | None = None
    baseline_model: str | None = None
    candidate_model: str | None = None
    change: dict[str, Any] | None = None


class ProposalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: str | None
    category: str
    suite_id: str | None
    baseline_model: str | None
    candidate_model: str | None
    change: dict[str, Any] | None
    status: str
    baseline_run_id: str | None
    candidate_run_id: str | None
    comparison: dict[str, Any] | None
    recommendation: str | None
    created_at: datetime
    updated_at: datetime


class ProposalList(BaseModel):
    items: list[ProposalRead]
    total: int
