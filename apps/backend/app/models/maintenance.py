"""Maintenance Agent models (spec §11, §14).

maintenance_issues  -- deduplicated problems (by log fingerprint)
maintenance_runs    -- analysis / fix attempts for an issue
git_actions         -- audit trail of every Git operation the agent performs
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, pk_column, utcnow


class IssueStatus(str, enum.Enum):
    OPEN = "OPEN"
    ANALYZING = "ANALYZING"
    FIX_PROPOSED = "FIX_PROPOSED"  # a fix is ready and awaiting human approval
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"
    IGNORED = "IGNORED"


class RunStatus(str, enum.Enum):
    ANALYZED = "ANALYZED"
    PATCHED = "PATCHED"
    TESTED = "TESTED"
    PR_OPENED = "PR_OPENED"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class Severity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MaintenanceIssue(Base):
    __tablename__ = "maintenance_issues"

    id: Mapped[str] = pk_column()
    fingerprint: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    service: Mapped[str | None] = mapped_column(String(64), nullable=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default=Severity.MEDIUM.value)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=IssueStatus.OPEN.value, index=True
    )
    occurrences: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sample: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    runs: Mapped[list[MaintenanceRun]] = relationship(
        back_populates="issue",
        cascade="all, delete-orphan",
        order_by="MaintenanceRun.created_at",
    )


class MaintenanceRun(Base):
    __tablename__ = "maintenance_runs"

    id: Mapped[str] = pk_column()
    issue_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("maintenance_issues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=RunStatus.ANALYZED.value
    )
    branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    patch: Mapped[str | None] = mapped_column(Text, nullable=True)
    tests_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    pr_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    risk: Mapped[str | None] = mapped_column(String(16), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    issue: Mapped[MaintenanceIssue] = relationship(back_populates="runs")


class GitAction(Base):
    __tablename__ = "git_actions"

    id: Mapped[str] = pk_column()
    run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("maintenance_runs.id", ondelete="CASCADE"), nullable=True
    )
    issue_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("maintenance_issues.id", ondelete="CASCADE"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
