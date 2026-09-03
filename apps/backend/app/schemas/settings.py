"""Runtime settings schemas (ROADMAP PR 15 config UI)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WebConfigRead(BaseModel):
    enabled: bool
    provider: str
    url: str
    has_api_key: bool
    max_results: int
    fetch_timeout: float
    max_bytes: int
    allow_private_ips: bool
    allowlist: list[str]
    denylist: list[str]


class WebConfigUpdate(BaseModel):
    """Partial update — only provided fields change."""

    enabled: bool | None = None
    provider: str | None = Field(default=None, pattern="^(none|searxng|json)$")
    url: str | None = None
    api_key: str | None = None
    max_results: int | None = Field(default=None, ge=1, le=25)
    fetch_timeout: float | None = Field(default=None, gt=0, le=120)
    max_bytes: int | None = Field(default=None, ge=1000, le=50_000_000)
    allow_private_ips: bool | None = None
    allowlist: list[str] | None = None
    denylist: list[str] | None = None
