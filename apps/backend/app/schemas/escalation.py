"""Escalation API schemas (spec §10, §15, M7)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EscalationContextIn(BaseModel):
    project_context: str = ""
    environment: str = ""
    source_excerpts: str = ""
    logs: str = ""
    tests_executed: str = ""
    hypothesis: str = ""
    constraints: str = ""
    expected_output: str = ""
    request: str = ""


class EscalationPrepare(BaseModel):
    objective: str = Field(min_length=1)
    target: str = "chatgpt"
    context: EscalationContextIn | None = None


class ExternalResponseImport(BaseModel):
    escalation_id: str
    response: str = Field(min_length=1)


class EscalationValidate(BaseModel):
    approved: bool
    notes: str | None = None
    decided_by: str = "operator"


class EscalationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    subject_type: str
    subject_id: str | None
    target: str
    objective: str
    package: str
    correlation_id: str
    status: str
    response: str | None
    validation: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class EscalationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    subject_type: str
    target: str
    objective: str
    status: str
    correlation_id: str
    created_at: datetime


class EscalationList(BaseModel):
    items: list[EscalationSummary]
    total: int
