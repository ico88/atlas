"""Ollama provider — local LLM inference (spec §4, M2).

Talks to an Ollama server over HTTP. All methods degrade gracefully: if the
server is unreachable, ``is_available`` returns False and the router falls back
to the echo provider.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

import httpx

from app.ai.base import ChatMessage, ModelInfo
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                return resp.status_code == 200
        except (httpx.HTTPError, OSError):
            return False

    async def list_models(self) -> list[ModelInfo]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, OSError) as exc:
            logger.warning("ollama list_models failed: %s", exc)
            return []

        models: list[ModelInfo] = []
        for entry in data.get("models", []):
            details = entry.get("details") or {}
            models.append(
                ModelInfo(
                    name=entry.get("name", "unknown"),
                    provider=self.name,
                    family=details.get("family"),
                )
            )
        return models

    async def stream_chat(
        self, messages: list[ChatMessage], model: str
    ) -> AsyncIterator[str]:
        settings = get_settings()
        options: dict[str, int] = {}
        if settings.ollama_num_ctx:
            options["num_ctx"] = settings.ollama_num_ctx
        if settings.ollama_num_predict:
            options["num_predict"] = settings.ollama_num_predict
        payload: dict[str, object] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            # Keep the model resident so a follow-up "ciao" doesn't reload it.
            "keep_alive": settings.ollama_keep_alive,
        }
        if options:
            payload["options"] = options
        async with (
            httpx.AsyncClient(timeout=None) as client,
            client.stream("POST", f"{self._base_url}/api/chat", json=payload) as resp,
        ):
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                piece = (chunk.get("message") or {}).get("content", "")
                if piece:
                    yield piece
                if chunk.get("done"):
                    break
