"""Web tools schemas (ROADMAP PR 15)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WebSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1024)
    limit: int | None = Field(default=None, ge=1, le=25)
    fetch_bodies: bool = True


class Citation(BaseModel):
    title: str
    url: str
    snippet: str
    score: float


class WebSearchResponse(BaseModel):
    query: str
    provider: str
    count: int
    citations: list[Citation]


class WebFetchRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class WebFetchResponse(BaseModel):
    url: str
    final_url: str
    status: int
    content_type: str
    title: str
    text: str
    truncated: bool
    bytes_read: int


class WebPolicyResponse(BaseModel):
    enabled: bool
    provider: str
    allow_private_ips: bool
    allowlist: list[str]
    denylist: list[str]
    max_bytes: int
    timeout: float
