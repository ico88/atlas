"""Fleet deployment models (ROADMAP PR 21 / PR 22).

A **deployment** rolls a target version out to the fleet: a small **canary** wave
first, then — only if the canary passes a **health gate** — the rest, in a rolling
wave. Offline nodes are skipped (reconciled later); incompatible nodes are skipped
with a reason; any failure triggers a **rollback** to the previous version.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, pk_column, utcnow


class DeploymentStatus(str, enum.Enum):
    CANARY = "CANARY"          # canary wave updating, awaiting the health gate
    ROLLING = "ROLLING"        # canary passed, rolling out to the rest
    COMPLETED = "COMPLETED"    # every eligible node healthy on the target
    ROLLED_BACK = "ROLLED_BACK"  # a failure reverted the fleet to the previous version
    FAILED = "FAILED"


class TargetStatus(str, enum.Enum):
    PENDING = "PENDING"            # eligible, not yet told to update
    UPDATING = "UPDATING"         # desired version set, awaiting the node's report
    HEALTHY = "HEALTHY"           # reported the target version and healthy
    FAILED = "FAILED"             # reported unhealthy / wrong version
    SKIPPED_OFFLINE = "SKIPPED_OFFLINE"    # offline at planning time (reconcile later)
    INCOMPATIBLE = "INCOMPATIBLE"          # current version below the compatibility floor


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[str] = pk_column()
    target_version: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    strategy: Mapped[str] = mapped_column(String(32), nullable=False, default="canary")
    canary_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DeploymentStatus.CANARY.value, index=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    targets: Mapped[list[DeploymentTarget]] = relationship(
        back_populates="deployment",
        cascade="all, delete-orphan",
        order_by="DeploymentTarget.created_at",
    )


class DeploymentTarget(Base):
    __tablename__ = "deployment_targets"

    id: Mapped[str] = pk_column()
    deployment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_pk: Mapped[str] = mapped_column(String(36), nullable=False)
    node_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    from_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    wave: Mapped[str] = mapped_column(String(16), nullable=False, default="rollout")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TargetStatus.PENDING.value
    )
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    deployment: Mapped[Deployment] = relationship(back_populates="targets")
