"""AI Router — provider/model selection (spec §9).

Sprint-scope policy (M2): prefer LOCAL inference (Ollama) when available, and
fall back to the echo provider otherwise. The interface is designed so richer
scoring (complexity/privacy/cost/latency) can be added later without changing
callers.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from app.ai.base import ChatProvider
from app.ai.echo import ECHO_MODEL, EchoProvider
from app.ai.ollama import OllamaProvider
from app.core.config import get_settings
from app.models.conversation import ChatMode

logger = logging.getLogger(__name__)

# Cache the Ollama reachability probe so a chat turn doesn't pay a health round
# trip every time (refreshed after ai_available_cache_seconds).
_avail_cache: dict[str, float | bool] = {"ok": False, "ts": 0.0}


async def _ollama_available(provider: OllamaProvider) -> bool:
    settings = get_settings()
    ttl = settings.ai_available_cache_seconds
    now = time.monotonic()
    if ttl > 0 and bool(_avail_cache["ok"]) and (now - float(_avail_cache["ts"])) < ttl:
        return True
    ok = await provider.is_available()
    _avail_cache["ok"] = ok
    _avail_cache["ts"] = now
    return ok


@dataclass
class RoutingDecision:
    provider: ChatProvider
    model: str
    reason: str


async def select(mode: str = ChatMode.AUTO.value, requested_model: str | None = None):
    """Choose a provider + model for the given mode."""

    settings = get_settings()
    echo = EchoProvider()

    # External/manual modes are not implemented in M2 -> use local fallback.
    ollama_enabled = bool(settings.ollama_url) and mode in (
        ChatMode.AUTO.value,
        ChatMode.LOCAL.value,
    )

    if ollama_enabled:
        ollama = OllamaProvider(settings.ollama_url)
        if await _ollama_available(ollama):
            model = requested_model or settings.default_model
            if not model:
                models = await ollama.list_models()
                model = models[0].name if models else ""
            if model:
                return RoutingDecision(ollama, model, reason="local ollama")
        logger.info("ollama unavailable; falling back to echo provider")

    return RoutingDecision(echo, requested_model or ECHO_MODEL, reason="echo fallback")


async def available_providers() -> list[ChatProvider]:
    """Providers currently usable (for the model registry refresh)."""

    settings = get_settings()
    providers: list[ChatProvider] = [EchoProvider()]
    if settings.ollama_url:
        ollama = OllamaProvider(settings.ollama_url)
        if await ollama.is_available():
            providers.append(ollama)
    return providers
