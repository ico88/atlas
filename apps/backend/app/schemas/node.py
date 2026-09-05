"""Pydantic schemas for the Node federation API (spec §8, §15)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NodeRegister(BaseModel):
    node_id: str = Field(min_length=1, max_length=128)
    hostname: str | None = None
    label: str | None = None
    version: str | None = None
    capabilities: dict[str, Any] | None = None
    hardware: dict[str, Any] | None = None


class NodeHeartbeat(BaseModel):
    status: str = "online"
    health: dict[str, Any] | None = None


class NodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    node_id: str
    hostname: str | None
    label: str | None
    version: str | None
    desired_version: str | None = None
    quarantined: bool = False
    status: str
    online: bool = False
    capabilities: dict[str, Any] | None
    hardware: dict[str, Any] | None
    last_heartbeat: datetime | None
    created_at: datetime


class NodeList(BaseModel):
    items: list[NodeRead]
    total: int
    online: int
