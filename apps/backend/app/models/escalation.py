"""Manual escalation model (spec §10, §14-adjacent, M7).

Represents a self-sufficient package prepared for a human to paste into ChatGPT
Plus / Claude Pro, plus the pasted response — which is UNTRUSTED until a human
validates it. The platform never automates browser/cookies/sessions (§10).
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, new_uuid, pk_column, utcnow


class EscalationTarget(str, enum.Enum):
    CHATGPT = "chatgpt"
    CLAUDE = "claude"


class EscalationStatus(str, enum.Enum):
    PREPARED = "PREPARED"
    RESPONSE_IMPORTED = "RESPONSE_IMPORTED"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"


class Escalation(Base):
    __tablename__ = "escalations"

    id: Mapped[str] = pk_column()
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    subject_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    target: Mapped[str] = mapped_column(
        String(16), nullable=False, default=EscalationTarget.CHATGPT.value
    )
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    package: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[str] = mapped_column(
        String(36), nullable=False, default=new_uuid, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=EscalationStatus.PREPARED.value, index=True
    )
    # Pasted response — treated as untrusted data, never executed automatically.
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
