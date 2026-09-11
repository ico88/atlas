"""Local fine-tuning models (ROADMAP: self-improvement / fine-tuning).

ATLAS already *selects and configures* the best among the models it has (evals →
adaptive routing → canary/health-gate/rollback). Fine-tuning is the step that
lets it *improve a model itself* from its own good interactions, without sending
data anywhere:

* a **dataset** is a named, curated collection of training **examples**
  (prompt → response pairs), most of them harvested automatically from
  positively-rated chat replies (feedback), the rest added by hand;
* a **job** trains a LoRA adapter on a dataset for a base model. Training runs
  on a GPU-capable node (dispatched as a remote task), never on the control
  plane; the finished adapter is then handed to the *same* eval-gate + canary
  guardrails as any other candidate before it can become the default.

This module is hardware-independent: it collects, curates and gates. The actual
training is done by the node agent's ``fine_tune`` executor, which honestly
requires a real training backend + GPU and reports failure when neither is
present rather than pretending.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, pk_column, utcnow


class FineTuneJobStatus(str, enum.Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        return self in {
            FineTuneJobStatus.COMPLETED,
            FineTuneJobStatus.FAILED,
            FineTuneJobStatus.CANCELLED,
        }


class FineTuneDataset(Base):
    __tablename__ = "finetune_datasets"

    id: Mapped[str] = pk_column()
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The model these examples are meant to improve (informational; a job can
    # target any base model).
    base_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    examples: Mapped[list[FineTuneExample]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="FineTuneExample.created_at",
    )


class FineTuneExample(Base):
    __tablename__ = "finetune_examples"
    __table_args__ = (
        # Same (prompt, response) is only harvested once per dataset.
        UniqueConstraint("dataset_id", "content_hash", name="uq_finetune_example_hash"),
    )

    id: Mapped[str] = pk_column()
    dataset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("finetune_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # feedback / manual / conversation
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quality: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    # An excluded example is kept but left out of the exported training set.
    included: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    dataset: Mapped[FineTuneDataset] = relationship(back_populates="examples")


class FineTuneJob(Base):
    __tablename__ = "finetune_jobs"

    id: Mapped[str] = pk_column()
    dataset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("finetune_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    base_model: Mapped[str] = mapped_column(String(128), nullable=False)
    # The name/tag the resulting adapter (fine-tuned model) is registered under.
    adapter_name: Mapped[str] = mapped_column(String(128), nullable=False)
    method: Mapped[str] = mapped_column(String(32), nullable=False, default="lora")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=FineTuneJobStatus.PENDING.value, index=True
    )
    # The remote training task this job dispatched (executed on a GPU node).
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    example_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hyperparams: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
