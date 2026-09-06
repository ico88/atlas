"""Attachment schemas (chat file upload, JSON + base64 — no multipart dep)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AttachmentUpload(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str | None = Field(default=None, max_length=128)
    data_b64: str = Field(min_length=1)  # base64-encoded file bytes
    conversation_id: str | None = None


class AttachmentRead(BaseModel):
    id: str
    filename: str
    content_type: str | None = None
    size_bytes: int
    chars: int
    preview: str
