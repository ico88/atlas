"""Auto-remediation audit trail (ROADMAP PR 25).

Every remediation action taken on a node — remediate (re-align to the desired
version), quarantine, reinstate — is recorded here for audit.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, pk_column, utcnow


class RemediationAction(str, enum.Enum):
    REMEDIATE = "remediate"      # set desired_version back to the fleet target
    QUARANTINE = "quarantine"    # exclude from scheduling
    REINSTATE = "reinstate"      # return to service


class RemediationEvent(Base):
    __tablename__ = "remediation_events"

    id: Mapped[str] = pk_column()
    node_ref: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    automatic: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
