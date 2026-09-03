"""Node enrollment schemas (ROADMAP PR 6)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EnrollmentCreate(BaseModel):
    node_id: str = Field(min_length=1, max_length=128)
    label: str | None = None
    created_by: str | None = None
    auto_approve: bool = False


class EnrollmentDecision(BaseModel):
    decided_by: str | None = None


class EnrollmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    node_id: str
    label: str | None
    status: str
    token_prefix: str
    created_by: str | None
    decided_by: str | None
    note: str | None
    created_at: datetime
    updated_at: datetime
    decided_at: datetime | None
    last_rotated_at: datetime | None
    last_used_at: datetime | None


class EnrollmentWithToken(EnrollmentRead):
    """Returned only at mint/rotate time — carries the one-time plaintext token."""

    token: str


class EnrollmentList(BaseModel):
    items: list[EnrollmentRead]
    total: int
