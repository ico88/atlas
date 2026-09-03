"""Runtime settings service (ROADMAP PR 15 config UI).

Operator-editable overrides that layer on top of environment defaults. Today it
backs the web-tools config (enable/provider/limits/allow-deny) so an operator can
turn web search on and point it at a provider from the UI without editing .env.

``get_effective_settings`` returns a fresh :class:`Settings` (env) with the stored
overrides applied, so existing code that takes a ``Settings`` keeps working.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db import get_sessionmaker
from app.models.app_setting import AppSetting

logger = logging.getLogger(__name__)

WEB_KEY = "web"
AI_KEY = "ai"

# AI overrides applied to Settings (operator-editable model defaults).
_AI_FIELDS: dict[str, str] = {"default_model": "default_model"}

# Friendly UI field name -> Settings attribute. Stored overrides use the UI names.
_WEB_FIELDS: dict[str, str] = {
    "enabled": "web_tools_enabled",
    "provider": "web_search_provider",
    "url": "web_search_url",
    "api_key": "web_search_api_key",
    "max_results": "web_max_results",
    "fetch_timeout": "web_fetch_timeout",
    "max_bytes": "web_fetch_max_bytes",
    "allow_private_ips": "web_allow_private_ips",
    "allowlist": "web_domain_allowlist",  # stored as a comma string (Settings shape)
    "denylist": "web_domain_denylist",
}
_SECRET_FIELDS = {"api_key"}


async def _get_row(session: AsyncSession, key: str) -> AppSetting | None:
    return await session.get(AppSetting, key)


async def get_overrides(key: str, session: AsyncSession | None = None) -> dict[str, Any]:
    if session is not None:
        row = await _get_row(session, key)
        return dict(row.value) if row else {}
    async with get_sessionmaker()() as s:
        row = await _get_row(s, key)
        return dict(row.value) if row else {}


async def set_overrides(
    key: str, patch: dict[str, Any], session: AsyncSession | None = None
) -> dict[str, Any]:
    async def _apply(s: AsyncSession) -> dict[str, Any]:
        row = await _get_row(s, key)
        merged = dict(row.value) if row else {}
        merged.update(patch)
        if row is None:
            s.add(AppSetting(key=key, value=merged))
        else:
            row.value = merged
        await s.commit()
        return merged

    if session is not None:
        return await _apply(session)
    async with get_sessionmaker()() as s:
        return await _apply(s)


async def get_effective_settings(session: AsyncSession | None = None) -> Settings:
    """Env-based Settings with stored web overrides applied."""

    settings = Settings()  # fresh from env/.env; never mutate the cached singleton
    web = await get_overrides(WEB_KEY, session)
    for ui_name, value in web.items():
        attr = _WEB_FIELDS.get(ui_name)
        if attr is not None and value is not None:
            setattr(settings, attr, value)
    ai = await get_overrides(AI_KEY, session)
    for ui_name, value in ai.items():
        attr = _AI_FIELDS.get(ui_name)
        if attr is not None and value is not None:
            setattr(settings, attr, value)
    return settings


async def set_ai_config(
    patch: dict[str, Any], session: AsyncSession | None = None
) -> dict[str, Any]:
    clean = {k: v for k, v in patch.items() if k in _AI_FIELDS and v is not None}
    await set_overrides(AI_KEY, clean, session)
    logger.info("ai config updated", extra={"event": "ai_config_updated"})
    return await get_ai_config_public(session)


async def get_ai_config_public(session: AsyncSession | None = None) -> dict[str, Any]:
    settings = await get_effective_settings(session)
    return {"default_model": settings.default_model}


def _normalise_web_patch(patch: dict[str, Any]) -> dict[str, Any]:
    """Keep only known web fields; coerce list allow/deny into comma strings."""

    clean: dict[str, Any] = {}
    for ui_name, value in patch.items():
        if ui_name not in _WEB_FIELDS or value is None:
            continue
        if ui_name in ("allowlist", "denylist") and isinstance(value, list):
            value = ",".join(str(v).strip() for v in value if str(v).strip())
        clean[ui_name] = value
    return clean


async def set_web_config(
    patch: dict[str, Any], session: AsyncSession | None = None
) -> dict[str, Any]:
    clean = _normalise_web_patch(patch)
    await set_overrides(WEB_KEY, clean, session)
    logger.info("web config updated", extra={"event": "web_config_updated"})
    return await get_web_config_public(session)


async def get_web_config_public(session: AsyncSession | None = None) -> dict[str, Any]:
    """Effective web config for the UI. The API key is masked to a boolean."""

    settings = await get_effective_settings(session)
    return {
        "enabled": settings.web_tools_enabled,
        "provider": settings.web_search_provider,
        "url": settings.web_search_url,
        "has_api_key": bool(settings.web_search_api_key),
        "max_results": settings.web_max_results,
        "fetch_timeout": settings.web_fetch_timeout,
        "max_bytes": settings.web_fetch_max_bytes,
        "allow_private_ips": settings.web_allow_private_ips,
        "allowlist": settings.web_allowlist,
        "denylist": settings.web_denylist,
    }
