"""Echo provider — a dependency-free local fallback.

Used when no real LLM (Ollama) is reachable, so chat, history and the API work
in development and tests without any model. It simply streams back a short,
deterministic reply derived from the user's last message.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from app.ai.base import ChatMessage, ModelInfo
from app.core.config import get_settings

ECHO_MODEL = "echo-local"


class EchoProvider:
    name = "echo"

    async def is_available(self) -> bool:
        return True

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(name=ECHO_MODEL, provider=self.name, context_length=8192)]

    async def stream_chat(
        self, messages: list[ChatMessage], model: str
    ) -> AsyncIterator[str]:
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        )
        reply = (
            f"You said: {last_user} "
            "— (ATLAS local echo model; configure Ollama for real responses.)"
        )
        delay = get_settings().chat_stream_delay
        for word in reply.split(" "):
            if delay:
                await asyncio.sleep(delay)
            yield word + " "
