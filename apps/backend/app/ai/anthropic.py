"""Anthropic runtime adapter (multi-runtime Fase 3 / M9).

Talks to the Anthropic Messages API — a different wire format from OpenAI, so it
needs its own adapter (OpenAI, llama.cpp, LocalAI and vLLM all share
``OpenAICompatAdapter``). Cloud runtimes are only ever reached when a deployment
is registered for them AND privacy/policy allow it (see gateway + MULTI_RUNTIME.md).
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

import httpx

from app.ai.base import ChatMessage, ModelInfo, RuntimeHealth, RuntimeState

logger = logging.getLogger(__name__)

_API = "https://api.anthropic.com"
_VERSION = "2023-06-01"


def parse_anthropic_sse(line: str) -> str | None:
    """Pure: extract the incremental text from one Anthropic stream line.

    Anthropic emits ``content_block_delta`` events carrying ``text_delta``s.
    Returns the delta text, or ``None`` for other event types / unparseable lines.
    """

    line = line.strip()
    if not line.startswith("data:"):
        return None
    data = line[len("data:") :].strip()
    if not data:
        return None
    try:
        evt = json.loads(data)
    except json.JSONDecodeError:
        return None
    if evt.get("type") != "content_block_delta":
        return None
    delta = evt.get("delta") or {}
    if delta.get("type") != "text_delta":
        return None
    return delta.get("text") or None


def _split_system(messages: list[ChatMessage]) -> tuple[str | None, list[dict]]:
    """Anthropic takes the system prompt as a top-level field, not a message."""

    system_parts = [m.content for m in messages if m.role == "system"]
    convo = [
        {"role": m.role, "content": m.content}
        for m in messages
        if m.role in ("user", "assistant")
    ]
    system = "\n\n".join(system_parts) if system_parts else None
    return system, convo


class AnthropicAdapter:
    name = "anthropic"

    def __init__(
        self,
        api_key: str | None,
        *,
        base_url: str = _API,
        name: str = "anthropic",
        max_tokens: int = 1024,
        timeout: float = 10.0,
    ) -> None:
        self.name = name
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._max_tokens = max_tokens
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": self._api_key or "",
            "anthropic-version": _VERSION,
        }

    async def is_available(self) -> bool:
        return bool(self._api_key)

    async def health(self) -> RuntimeHealth:
        if not self._api_key:
            return RuntimeHealth(RuntimeState.DOWN, "no API key configured")
        return RuntimeHealth(RuntimeState.UP, "api key present")

    async def list_models(self) -> list[ModelInfo]:
        # The Messages API has no public list endpoint; models are declared via
        # deployments. Return nothing rather than guessing.
        return []

    async def stream_chat(
        self, messages: list[ChatMessage], model: str
    ) -> AsyncIterator[str]:
        system, convo = _split_system(messages)
        payload: dict[str, object] = {
            "model": model,
            "messages": convo,
            "max_tokens": self._max_tokens,
            "stream": True,
        }
        if system:
            payload["system"] = system
        async with (
            httpx.AsyncClient(timeout=None) as client,
            client.stream(
                "POST", f"{self._base_url}/v1/messages", json=payload, headers=self._headers()
            ) as resp,
        ):
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                piece = parse_anthropic_sse(line)
                if piece:
                    yield piece
