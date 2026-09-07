"""Service accounts — non-human API identities (ROADMAP R5).

For automation/integrations that need to call the ATLAS API without a human
login. A long-lived token is issued once (only its hash is stored) and can be
scoped by role and revoked.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, pk_column, utcnow


class ServiceAccount(Base):
    __tablename__ = "service_accounts"

    id: Mapped[str] = pk_column()
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="user")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
