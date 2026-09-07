"""Encrypted secret store (ROADMAP R5 — secret manager).

Secrets are stored **encrypted at rest** (Fernet/AES-128-CBC+HMAC). Only the
ciphertext is persisted; plaintext exists only transiently when a secret is
written or explicitly read back by an admin.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, pk_column, utcnow


class Secret(Base):
    __tablename__ = "secrets"

    id: Mapped[str] = pk_column()
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
