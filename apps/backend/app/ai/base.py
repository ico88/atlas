"""Provider-agnostic chat interfaces (spec §2 provider-agnostic, §9)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class ModelInfo:
    name: str
    provider: str
    family: str | None = None
    context_length: int | None = None


@runtime_checkable
class ChatProvider(Protocol):
    """A pluggable chat backend. The core never depends on a specific one."""

    name: str

    async def is_available(self) -> bool:
        """Whether the provider can currently serve requests."""

    async def list_models(self) -> list[ModelInfo]:
        """Models this provider exposes."""

    def stream_chat(
        self, messages: list[ChatMessage], model: str
    ) -> AsyncIterator[str]:
        """Stream the assistant reply as text chunks."""
