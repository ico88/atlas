"""Approval API schemas (spec §15)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str | None
    subject_type: str | None
    subject_id: str | None
    action: str
    status: str
    requested_by: str | None
    decided_by: str | None
    reason: str | None
    created_at: datetime
    decided_at: datetime | None


class ApprovalDecision(BaseModel):
    decided_by: str = "operator"
    reason: str | None = None


class ApprovalList(BaseModel):
    items: list[ApprovalRead]
    total: int
