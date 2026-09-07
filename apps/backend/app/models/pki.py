"""Issued-certificate registry for the internal PKI (ROADMAP R5).

The CA key/cert live (encrypted) in the secret store; this table records each
certificate the CA issues so it can be listed and revoked. Private keys of issued
certs are never stored — they are returned once at issue time.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, pk_column, utcnow


class IssuedCert(Base):
    __tablename__ = "issued_certs"

    id: Mapped[str] = pk_column()
    serial: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    common_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    not_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
