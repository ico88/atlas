"""Schemas for runtimes, model deployments and model aliases (multi-runtime)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------------------- #
# Runtimes
# --------------------------------------------------------------------------- #
class RuntimeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    runtime_type: str = Field(min_length=1, max_length=32)
    endpoint: str | None = Field(default=None, max_length=255)
    api_key: str | None = Field(default=None, max_length=255)
    node_id: str | None = Field(default=None, max_length=128)
    version: str | None = Field(default=None, max_length=32)
    enabled: bool = True
    supports_streaming: bool = True
    supports_embeddings: bool = False
    supports_tools: bool = False
    supports_vision: bool = False
    max_concurrency: int = Field(default=1, ge=1)
    meta: dict[str, Any] | None = None


class RuntimeUpdate(BaseModel):
    endpoint: str | None = Field(default=None, max_length=255)
    api_key: str | None = Field(default=None, max_length=255)
    node_id: str | None = Field(default=None, max_length=128)
    version: str | None = Field(default=None, max_length=32)
    enabled: bool | None = None
    max_concurrency: int | None = Field(default=None, ge=1)
    meta: dict[str, Any] | None = None


class RuntimeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    runtime_type: str
    version: str | None
    endpoint: str | None
    node_id: str | None
    enabled: bool
    status: str
    supports_streaming: bool
    supports_embeddings: bool
    supports_tools: bool
    supports_vision: bool
    max_concurrency: int
    updated_at: datetime


class RuntimeList(BaseModel):
    items: list[RuntimeRead]
    total: int


class RuntimeHealthRead(BaseModel):
    id: str
    name: str
    runtime_type: str
    state: str
    detail: str
    circuit: str = "CLOSED"


# --------------------------------------------------------------------------- #
# Deployments
# --------------------------------------------------------------------------- #
class DeploymentCreate(BaseModel):
    model_key: str = Field(min_length=1, max_length=128)
    runtime_id: str = Field(min_length=1, max_length=36)
    runtime_model_name: str = Field(min_length=1, max_length=128)
    node_id: str | None = Field(default=None, max_length=128)
    priority: int = 100
    max_context: int | None = None
    max_concurrency: int = Field(default=1, ge=1)
    enabled: bool = True
    meta: dict[str, Any] | None = None


class DeploymentUpdate(BaseModel):
    runtime_model_name: str | None = Field(default=None, max_length=128)
    priority: int | None = None
    max_context: int | None = None
    max_concurrency: int | None = Field(default=None, ge=1)
    enabled: bool | None = None
    loaded: bool | None = None
    estimated_tokens_per_second: float | None = None
    meta: dict[str, Any] | None = None


class ModelDeploymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    model_key: str
    runtime_id: str
    node_id: str | None
    runtime_model_name: str
    loaded: bool
    status: str
    priority: int
    max_context: int | None
    max_concurrency: int
    estimated_tokens_per_second: float | None
    last_benchmark: datetime | None
    enabled: bool
    updated_at: datetime


class DeploymentList(BaseModel):
    items: list[ModelDeploymentRead]
    total: int


# --------------------------------------------------------------------------- #
# Aliases
# --------------------------------------------------------------------------- #
class AliasUpsert(BaseModel):
    alias: str = Field(min_length=1, max_length=64)
    targets: list[str] = Field(default_factory=list)
    description: str | None = Field(default=None, max_length=255)
    enabled: bool = True


class ModelAliasRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    alias: str
    targets: list[Any] | None
    description: str | None
    enabled: bool
    updated_at: datetime


class AliasList(BaseModel):
    items: list[ModelAliasRead]
    total: int


# --------------------------------------------------------------------------- #
# Routing policies (Fase 3 / M9)
# --------------------------------------------------------------------------- #
class PolicyUpsert(BaseModel):
    task_type: str = Field(min_length=1, max_length=64)
    required_capabilities: list[str] = Field(default_factory=list)
    preferred_alias: str | None = Field(default=None, max_length=64)
    privacy: str = Field(default="LOCAL_PREFERRED", max_length=24)
    fallback: list[str] = Field(default_factory=list)
    max_latency_ms: int | None = None
    priority: int = 100
    enabled: bool = True


class RoutingPolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_type: str
    required_capabilities: list[Any] | None
    preferred_alias: str | None
    privacy: str
    fallback: list[Any] | None
    max_latency_ms: int | None
    priority: int
    enabled: bool
    updated_at: datetime


class PolicyList(BaseModel):
    items: list[RoutingPolicyRead]
    total: int
