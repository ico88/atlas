"""OpenAI-compatible runtime adapter (multi-runtime Fase 1).

A single adapter for every engine that speaks the OpenAI wire format on
``/v1/chat/completions`` + ``/v1/models``:

- **llama.cpp** — ``llama-server`` (the recommended CPU/GGUF runtime);
- **LocalAI** — OpenAI-compatible local server;
- **vLLM** — its OpenAI server (GPU);
- **OpenAI** itself (cloud), by pointing ``base_url`` at ``https://api.openai.com``.

Only Ollama (native API) and Anthropic (different format) need their own adapters.
All methods degrade gracefully: an unreachable server reports DOWN and the router
routes around it.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

import httpx

from app.ai.base import ChatMessage, ModelInfo, RuntimeHealth, RuntimeState

logger = logging.getLogger(__name__)


def parse_sse_content(line: str) -> str | None:
    """Extract the incremental text from one SSE line of a chat-completions stream.

    Pure and dependency-free so it is unit-tested without a network. Returns the
    delta text, or ``None`` for keep-alives, ``[DONE]`` and unparseable lines.
    """

    line = line.strip()
    if not line.startswith("data:"):
        return None
    data = line[len("data:") :].strip()
    if not data or data == "[DONE]":
        return None
    try:
        chunk = json.loads(data)
    except json.JSONDecodeError:
        return None
    choices = chunk.get("choices") or []
    if not choices:
        return None
    delta = choices[0].get("delta") or {}
    content = delta.get("content")
    # Some servers put the text under message.content on the final chunk.
    if content is None:
        content = (choices[0].get("message") or {}).get("content")
    return content or None


class OpenAICompatAdapter:
    """Adapter for any OpenAI-compatible HTTP inference server."""

    def __init__(
        self,
        base_url: str,
        *,
        name: str = "openai_compat",
        api_key: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.name = name
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{self._base_url}/v1/models", headers=self._headers())
                return resp.status_code == 200
        except (httpx.HTTPError, OSError):
            return False

    async def health(self) -> RuntimeHealth:
        if await self.is_available():
            return RuntimeHealth(RuntimeState.UP, self._base_url)
        return RuntimeHealth(RuntimeState.DOWN, f"unreachable at {self._base_url}")

    async def list_models(self) -> list[ModelInfo]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._base_url}/v1/models", headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, OSError) as exc:
            logger.warning("%s list_models failed: %s", self.name, exc)
            return []
        return [
            ModelInfo(name=entry.get("id", "unknown"), provider=self.name)
            for entry in data.get("data", [])
        ]

    async def stream_chat(self, messages: list[ChatMessage], model: str) -> AsyncIterator[str]:
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
        }
        timeout = httpx.Timeout(self._timeout, read=max(self._timeout, 120.0))
        try:
            async with (
                httpx.AsyncClient(timeout=timeout) as client,
                client.stream(
                    "POST",
                    f"{self._base_url}/v1/chat/completions",
                    json=payload,
                    headers=self._headers(),
                ) as resp,
            ):
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    piece = parse_sse_content(line)
                    if piece:
                        yield piece
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"{self.name} response timed out") from exc
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Cannot connect to {self.name} at {self._base_url}") from exc
