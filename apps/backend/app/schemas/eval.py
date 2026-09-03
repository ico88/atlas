"""Evaluation schemas (ROADMAP PR 16)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SuiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None


class CaseCreate(BaseModel):
    input: str = Field(min_length=1)
    expected_substrings: list[str] | None = None
    forbidden_substrings: list[str] | None = None
    category: str = "quality"


class CaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    input: str
    expected_substrings: list[str] | None
    forbidden_substrings: list[str] | None
    category: str


class SuiteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    created_at: datetime


class SuiteDetail(SuiteRead):
    cases: list[CaseRead] = []


class SuiteList(BaseModel):
    items: list[SuiteRead]
    total: int


class RunRequest(BaseModel):
    model: str | None = None
    is_baseline: bool = False


class ResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    output: str | None
    passed: bool
    quality: float
    safety: float
    latency_ms: int | None


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    suite_id: str
    provider: str | None
    model: str | None
    status: str
    metrics: dict[str, Any] | None
    is_baseline: bool
    created_at: datetime
    completed_at: datetime | None


class RunDetail(RunRead):
    results: list[ResultRead] = []


class RunList(BaseModel):
    items: list[RunRead]
    total: int
