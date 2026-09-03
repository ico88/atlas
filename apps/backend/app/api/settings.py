"""Runtime settings API (ROADMAP PR 15 config UI).

Operator-editable overrides. Currently exposes the web-tools config so it can be
enabled and pointed at a provider from the UI. The API key is write-only: it is
never returned (only ``has_api_key`` is reported).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.settings import WebConfigRead, WebConfigUpdate
from app.services import settings_service

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


@router.get("/web", response_model=WebConfigRead)
async def get_web_config() -> WebConfigRead:
    return WebConfigRead.model_validate(await settings_service.get_web_config_public())


@router.put("/web", response_model=WebConfigRead)
async def update_web_config(payload: WebConfigUpdate) -> WebConfigRead:
    patch = payload.model_dump(exclude_none=True)
    return WebConfigRead.model_validate(await settings_service.set_web_config(patch))
