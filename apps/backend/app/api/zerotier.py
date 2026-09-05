"""ZeroTier overlay controller API (ROADMAP PR 7)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import zerotier_service
from app.services.zerotier_service import ZeroTierError

router = APIRouter(prefix="/api/v1/zerotier", tags=["zerotier"])


class AuthorizeRequest(BaseModel):
    authorized: bool = True


@router.get("/status")
async def status() -> dict[str, Any]:
    return await zerotier_service.status()


@router.get("/members")
async def members() -> dict[str, Any]:
    try:
        items = await zerotier_service.list_members()
    except ZeroTierError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"items": items, "total": len(items)}


@router.post("/members/{member_id}/authorize")
async def authorize(member_id: str, payload: AuthorizeRequest) -> dict[str, Any]:
    try:
        return await zerotier_service.authorize_member(member_id, payload.authorized)
    except ZeroTierError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
