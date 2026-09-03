"""Node enrollment model (ROADMAP PR 6).

Per-node credentials with a human approval gate. An admin creates an enrollment
(an invite) which mints a one-time secret token; the node presents it to
register/heartbeat/claim. The enrollment carries a lifecycle status so an
operator can **approve**, **reject**, **revoke**, or **rotate** a node's access
independently of the shared join token. Only the token's SHA-256 hash is stored.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, pk_column, utcnow


class EnrollmentStatus(str, enum.Enum):
    PENDING = "PENDING"    # invited / self-announced, awaiting approval
    APPROVED = "APPROVED"  # may claim and execute work
    REJECTED = "REJECTED"  # denied by an operator
    REVOKED = "REVOKED"    # previously approved, access withdrawn

    @property
    def can_claim(self) -> bool:
        return self is EnrollmentStatus.APPROVED

    @property
    def is_active(self) -> bool:
        """Whether the token is still usable at all (not denied/withdrawn)."""

        return self in {EnrollmentStatus.PENDING, EnrollmentStatus.APPROVED}


class NodeEnrollment(Base):
    __tablename__ = "node_enrollments"

    id: Mapped[str] = pk_column()
    node_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=EnrollmentStatus.PENDING.value, index=True
    )
    # SHA-256 of the secret token; the plaintext is shown only once at mint time.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    token_prefix: Mapped[str] = mapped_column(String(12), nullable=False)  # for display
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_rotated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
