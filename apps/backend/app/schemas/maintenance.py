"""Maintenance API schemas (spec §11, §15)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LogIngest(BaseModel):
    message: str = Field(min_length=1)
    service: str | None = None
    level: str | None = None
    event: str | None = None
    context: dict[str, Any] | None = None


class GitActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    action: str
    branch: str | None
    target: str | None
    allowed: bool
    detail: str | None
    created_at: datetime


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    issue_id: str
    status: str
    branch: str | None
    analysis: str | None
    patch: str | None
    tests_summary: str | None
    pr_url: str | None
    risk: str | None
    attempts: int
    created_at: datetime
    updated_at: datetime


class IssueSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    fingerprint: str
    title: str
    service: str | None
    severity: str
    status: str
    occurrences: int
    first_seen: datetime
    last_seen: datetime


class IssueDetail(IssueSummary):
    sample: dict[str, Any] | None = None
    runs: list[RunRead] = []


class IssueList(BaseModel):
    items: list[IssueSummary]
    total: int


class SandboxRequest(BaseModel):
    """Validate a patch against seed files in the real sandbox (ROADMAP PR 17).

    The check command is *not* accepted here — it comes only from server config,
    so this endpoint can never be used to run arbitrary commands.
    """

    files: dict[str, str] = Field(
        default_factory=dict, description="relative path -> file content to seed"
    )
    patch: str = Field(min_length=1, description="unified diff to apply and validate")


class SandboxResultRead(BaseModel):
    applied: bool
    passed: bool
    returncode: int | None = None
    command: str | None = None
    stdout: str = ""
    stderr: str = ""
    summary: str
    files: list[str] = []
