"""Provider/runtime-agnostic interfaces (spec §2 provider-agnostic, §9).

ALMA and the chat layer never talk to a concrete engine (Ollama, llama.cpp,
vLLM, OpenAI, …). They go through a ``RuntimeAdapter``: a small, uniform
interface every engine implements. New engines are added by writing one adapter
— no caller changes. ``ChatProvider`` is kept as a backward-compatible alias.
"""

from __future__ import annotations

import enum
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class RuntimeType(str, enum.Enum):
    """How a runtime speaks. One OpenAI-compatible adapter covers llama.cpp's
    ``llama-server``, LocalAI and vLLM's OpenAI server; Ollama and Anthropic
    have their own wire formats; ``echo`` is the dependency-free local fallback."""

    ECHO = "echo"
    OLLAMA = "ollama"
    OPENAI_COMPAT = "openai_compat"  # llama.cpp / LocalAI / vLLM (OpenAI wire)
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class RuntimeState(str, enum.Enum):
    UP = "UP"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"


class Capability(str, enum.Enum):
    """What a model/deployment can do. ALMA asks for capabilities, never names."""

    CHAT = "CHAT"
    REASONING = "REASONING"
    CODING = "CODING"
    SUMMARIZATION = "SUMMARIZATION"
    TRANSLATION = "TRANSLATION"
    RAG = "RAG"
    EMBEDDINGS = "EMBEDDINGS"
    VISION = "VISION"
    TOOL_CALLING = "TOOL_CALLING"
    JSON_OUTPUT = "JSON_OUTPUT"
    LONG_CONTEXT = "LONG_CONTEXT"


# Runtime types that reach an external (cloud) provider. Privacy LOCAL_ONLY must
# exclude these from routing candidates.
CLOUD_RUNTIME_TYPES: frozenset[str] = frozenset(
    {RuntimeType.OPENAI.value, RuntimeType.ANTHROPIC.value}
)


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


@dataclass
class RuntimeHealth:
    state: RuntimeState
    detail: str = ""

    @property
    def usable(self) -> bool:
        return self.state != RuntimeState.DOWN


@dataclass
class RoutingDecision:
    """What the router chose, and why — surfaced for explainability (§42)."""

    provider: RuntimeAdapter
    model: str
    reason: str
    runtime: str | None = None  # runtime name/type that will serve the request
    node: str | None = None  # node the runtime runs on (None = control plane)
    deployment_id: str | None = None
    max_concurrency: int = 0  # 0 = unlimited (used for slot reservation, Fase 4)
    score: float | None = None


@runtime_checkable
class RuntimeAdapter(Protocol):
    """A pluggable inference backend. The core never depends on a specific one."""

    name: str

    async def is_available(self) -> bool:
        """Whether the runtime can currently serve requests."""

    async def health(self) -> RuntimeHealth:
        """Structured health (UP / DEGRADED / DOWN) for the router to act on."""

    async def list_models(self) -> list[ModelInfo]:
        """Models this runtime exposes."""

    def stream_chat(
        self, messages: list[ChatMessage], model: str
    ) -> AsyncIterator[str]:
        """Stream the assistant reply as text chunks."""


# Backward-compatible alias: existing code imports ``ChatProvider``.
ChatProvider = RuntimeAdapter
