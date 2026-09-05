"""Pure Model Gateway logic (multi-runtime Fase 1): scoring, capability &
privacy filters, and OpenAI-compatible SSE parsing — no DB, no network."""

from __future__ import annotations

from app.ai import gateway
from app.ai.gateway import Privacy
from app.ai.openai_compat import parse_sse_content
from app.models.provider import LLMModel
from app.models.runtime import ModelDeployment, Runtime


def _dep(**over) -> ModelDeployment:
    data = {
        "model_key": "m", "runtime_id": "r", "runtime_model_name": "m:tag",
        "priority": 100, "estimated_tokens_per_second": None,
    }
    data.update(over)
    return ModelDeployment(**data)


def _rt(**over) -> Runtime:
    data = {"name": "rt", "runtime_type": "ollama", "node_id": None}
    data.update(over)
    return Runtime(**data)


def test_capabilities_ok():
    model = LLMModel(provider="p", name="n", capabilities={"CHAT": True, "CODING": True})
    assert gateway.capabilities_ok(model, {"CHAT"}) is True
    assert gateway.capabilities_ok(model, {"CHAT", "CODING"}) is True
    assert gateway.capabilities_ok(model, {"VISION"}) is False
    assert gateway.capabilities_ok(model, set()) is True  # no requirement -> ok
    assert gateway.capabilities_ok(None, {"CHAT"}) is False


def test_capabilities_accepts_list_shape():
    model = LLMModel(provider="p", name="n", capabilities=["chat", "reasoning"])
    assert gateway.model_capabilities(model) == {"CHAT", "REASONING"}


def test_privacy_local_only_excludes_cloud():
    assert gateway.privacy_allows("ollama", Privacy.LOCAL_ONLY, cloud_allowed=True) is True
    assert gateway.privacy_allows("openai", Privacy.LOCAL_ONLY, cloud_allowed=True) is False


def test_privacy_cloud_gated_by_global_flag():
    # LOCAL_PREFERRED lets cloud in only when globally allowed.
    pref = Privacy.LOCAL_PREFERRED
    assert gateway.privacy_allows("anthropic", pref, cloud_allowed=False) is False
    assert gateway.privacy_allows("anthropic", pref, cloud_allowed=True) is True
    # CLOUD_REQUIRED excludes local runtimes entirely.
    assert gateway.privacy_allows("ollama", Privacy.CLOUD_REQUIRED, cloud_allowed=True) is False


def test_score_prefers_local_and_priority():
    model = LLMModel(provider="p", name="n", capabilities={"CHAT": True})
    local = gateway.score_candidate(
        _dep(priority=100), _rt(runtime_type="ollama"), model,
        required={"CHAT"}, local_first=True, runtime_priority=["ollama"],
    )
    cloud = gateway.score_candidate(
        _dep(priority=100), _rt(runtime_type="openai"), model,
        required={"CHAT"}, local_first=True, runtime_priority=["ollama"],
    )
    assert local > cloud  # the local bonus wins with equal priority


def test_score_respects_runtime_priority_order():
    model = LLMModel(provider="p", name="n")
    prio = ["llama_cpp", "ollama"]
    llama = gateway.score_candidate(
        _dep(), _rt(runtime_type="llama_cpp"), model,
        required=set(), local_first=False, runtime_priority=prio,
    )
    ollama = gateway.score_candidate(
        _dep(), _rt(runtime_type="ollama"), model,
        required=set(), local_first=False, runtime_priority=prio,
    )
    assert llama > ollama  # earlier in the priority list scores higher


def test_score_alias_rank_dominates():
    model = LLMModel(provider="p", name="n")
    first = gateway.score_candidate(
        _dep(), _rt(), model, required=set(), local_first=False,
        runtime_priority=[], alias_rank=0,
    )
    second = gateway.score_candidate(
        _dep(), _rt(), model, required=set(), local_first=False,
        runtime_priority=[], alias_rank=1,
    )
    assert first > second


def test_adapter_factory_maps_types():
    from app.ai.echo import EchoProvider
    from app.ai.ollama import OllamaProvider
    from app.ai.openai_compat import OpenAICompatAdapter

    assert isinstance(gateway.adapter_for(_rt(runtime_type="echo")), EchoProvider)
    assert isinstance(
        gateway.adapter_for(_rt(runtime_type="ollama", endpoint="http://x")), OllamaProvider
    )
    assert isinstance(
        gateway.adapter_for(_rt(runtime_type="llama_cpp", endpoint="http://x")),
        OpenAICompatAdapter,
    )


def test_sse_parsing():
    assert parse_sse_content('data: {"choices":[{"delta":{"content":"Hi"}}]}') == "Hi"
    assert parse_sse_content("data: [DONE]") is None
    assert parse_sse_content(": keep-alive") is None
    assert parse_sse_content("data: not-json") is None
    # Final-chunk shape (content under message).
    assert parse_sse_content('data: {"choices":[{"message":{"content":"end"}}]}') == "end"
