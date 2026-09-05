"""Fleet compliance & remediation API schemas (ROADMAP PR 24 / PR 25)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DesiredState(BaseModel):
    target_version: str = ""
    required_capabilities: list[str] = Field(default_factory=list)
    min_online: int = 0


class NodeCompliance(BaseModel):
    node_ref: str | None
    online: bool
    quarantined: bool
    version: str | None
    compliant: bool
    issues: list[str] = []
    diagnosis: str | None = None
    recommended_action: str | None = None


class ComplianceReport(BaseModel):
    summary: dict[str, Any]
    desired: DesiredState
    nodes: list[NodeCompliance]


class RemediateRequest(BaseModel):
    node_ref: str
    action: str = Field(pattern="^(remediate|quarantine|reinstate)$")
    reason: str | None = None


class RemediationEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    node_ref: str
    action: str
    reason: str | None
    automatic: bool
    created_at: datetime
