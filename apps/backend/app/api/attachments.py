"""Chat attachment upload API (JSON + base64, no multipart dependency)."""

from __future__ import annotations

import base64
import binascii

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.attachment import AttachmentRead, AttachmentUpload
from app.services import attachment_service

router = APIRouter(prefix="/api/v1", tags=["attachments"])


@router.post("/chat/attachments", response_model=AttachmentRead, status_code=201)
async def upload_attachment(
    payload: AttachmentUpload, session: AsyncSession = Depends(get_session)
) -> AttachmentRead:
    try:
        raw = base64.b64decode(payload.data_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid base64: {exc}") from exc

    att, err = await attachment_service.create_attachment(
        session,
        filename=payload.filename,
        content_type=payload.content_type,
        raw=raw,
        conversation_id=payload.conversation_id,
    )
    if err or att is None:
        # 415 for unsupported/too-large/empty content.
        raise HTTPException(status_code=415, detail=err or "could not read file")
    return AttachmentRead(
        id=att.id,
        filename=att.filename,
        content_type=att.content_type,
        size_bytes=att.size_bytes,
        chars=len(att.text_content),
        preview=att.text_content[:200],
    )
