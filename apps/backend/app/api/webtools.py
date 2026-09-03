"""Web tools API (ROADMAP PR 15): safe search & fetch with citations."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas.webtools import (
    WebFetchRequest,
    WebFetchResponse,
    WebPolicyResponse,
    WebSearchRequest,
    WebSearchResponse,
)
from app.services import settings_service, webtools_service
from app.webtools import policy as pol

router = APIRouter(prefix="/api/v1/web", tags=["web-tools"])


@router.get("/policy", response_model=WebPolicyResponse)
async def get_policy() -> WebPolicyResponse:
    """Report the active web-tools policy (no secrets)."""

    settings = await settings_service.get_effective_settings()
    p = webtools_service.build_policy(settings)
    return WebPolicyResponse(
        enabled=settings.web_tools_enabled,
        provider=settings.web_search_provider,
        allow_private_ips=p.allow_private_ips,
        allowlist=list(p.allowlist),
        denylist=list(p.denylist),
        max_bytes=p.max_bytes,
        timeout=p.timeout,
    )


@router.post("/search", response_model=WebSearchResponse)
async def web_search(payload: WebSearchRequest) -> WebSearchResponse:
    try:
        result = await webtools_service.search(
            payload.query, limit=payload.limit, fetch_bodies=payload.fetch_bodies
        )
    except webtools_service.WebToolsDisabled as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return WebSearchResponse.model_validate(result)


@router.post("/fetch", response_model=WebFetchResponse)
async def web_fetch(payload: WebFetchRequest) -> WebFetchResponse:
    try:
        result = await webtools_service.fetch(payload.url)
    except webtools_service.WebToolsDisabled as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except pol.PolicyError as exc:
        raise HTTPException(status_code=400, detail=f"blocked by policy: {exc}") from exc
    return WebFetchResponse(
        url=result.url,
        final_url=result.final_url,
        status=result.status,
        content_type=result.content_type,
        title=result.title,
        text=result.text,
        truncated=result.truncated,
        bytes_read=result.bytes_read,
    )
