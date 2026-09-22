"""Runtime, ModelDeployment & ModelAlias registries (multi-runtime Fase 1).

The heart of the multi-runtime design: a **model**, a **runtime** and a **node**
are separate things, joined by a **deployment**. The same model can exist on many
nodes/runtimes; ALMA asks for a capability (or an alias) and the router picks the
best deployment.

    Runtime (how it runs)  ─┐
    LLMModel (what it is)  ─┼─►  ModelDeployment (model × runtime × node)
    Node (where it runs)   ─┘

    ModelAlias ("atlas.general") ─► ordered preference over model_keys
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, pk_column, utcnow


class Runtime(Base):
    """A registered inference engine instance (Ollama, llama.cpp, vLLM, …)."""

    __tablename__ = "runtimes"

    id: Mapped[str] = pk_column()
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    runtime_type: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Encrypted Fernet ciphertext; deliberately not exposed by RuntimeRead.
    api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    node_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    supports_streaming: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supports_embeddings: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_tools: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_vision: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class ModelDeployment(Base):
    """A model made available through a specific runtime (and optionally node)."""

    __tablename__ = "model_deployments"

    id: Mapped[str] = pk_column()
    model_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    runtime_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    node_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    # The name the runtime itself uses for this model (may differ from model_key).
    runtime_model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    loaded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="READY")
    # Loading strategy (Fase 4): ALWAYS_LOADED | ON_DEMAND | PINNED | AUTO_UNLOAD.
    load_policy: Mapped[str] = mapped_column(String(16), nullable=False, default="ON_DEMAND")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    max_context: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    estimated_tokens_per_second: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_benchmark: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class RoutingPolicy(Base):
    """How a *kind of task* should be routed (Fase 3 / M9).

    Maps a task type ("coding", "translation", "chat") to the capabilities it
    needs, a preferred alias, a privacy level and an ordered fallback of aliases.
    ALMA names a task type; the gateway turns it into a concrete deployment.
    """

    __tablename__ = "routing_policies"

    id: Mapped[str] = pk_column()
    task_type: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    required_capabilities: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    preferred_alias: Mapped[str | None] = mapped_column(String(64), nullable=True)
    privacy: Mapped[str] = mapped_column(String(24), nullable=False, default="LOCAL_PREFERRED")
    max_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fallback: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class ModelAlias(Base):
    """A stable name ALMA uses ("atlas.general") mapped to an ordered list of
    preferred ``model_key`` values. Swapping a model needs no code change."""

    __tablename__ = "model_aliases"

    id: Mapped[str] = pk_column()
    alias: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    targets: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
