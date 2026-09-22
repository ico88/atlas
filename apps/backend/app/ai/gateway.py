"""Model Gateway — pick model × runtime × node for a request (multi-runtime).

ALMA/chat asks for *capabilities* (or an alias) and a *privacy* level; the gateway
finds every eligible deployment, scores them, and returns the best healthy one as a
:class:`RoutingDecision`. Adding a new engine is writing one adapter and a factory
line — the scoring and callers never change.

Scoring (concept §12), kept as a pure function so it is unit-tested directly::

    score = capability fit
          + deployment.priority
          + runtime-type preference (soft)
          + local bonus (when local_first)
          + throughput (measured tokens/s, when benchmarked)
          - deployment ordinal (registration tie-break)

This is the Fase-1 scorer: node load and free-VRAM terms are left as clearly
marked TODOs for Fase 2 (they need live telemetry to be meaningful).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import circuit, reservation
from app.ai.anthropic import AnthropicAdapter
from app.ai.base import (
    CLOUD_RUNTIME_TYPES,
    RoutingDecision,
    RuntimeAdapter,
    RuntimeType,
)
from app.ai.echo import EchoProvider
from app.ai.ollama import OllamaProvider
from app.ai.openai_compat import OpenAICompatAdapter
from app.core.config import get_settings
from app.models.provider import LLMModel
from app.models.runtime import ModelAlias, ModelDeployment, RoutingPolicy, Runtime

logger = logging.getLogger(__name__)


class Privacy(str):
    LOCAL_ONLY = "LOCAL_ONLY"
    LOCAL_PREFERRED = "LOCAL_PREFERRED"
    CLOUD_ALLOWED = "CLOUD_ALLOWED"
    CLOUD_REQUIRED = "CLOUD_REQUIRED"


# --------------------------------------------------------------------------- #
# Adapter factory: runtime_type (a free string in the DB) -> adapter instance.
# Several types share the OpenAI-compatible adapter — that is the whole point.
# --------------------------------------------------------------------------- #
_OPENAI_COMPAT_TYPES = {
    RuntimeType.OPENAI_COMPAT.value,
    RuntimeType.OPENAI.value,
    RuntimeType.DEEPSEEK.value,
    "llama_cpp",
    "localai",
    "vllm",
    "sglang",
}


def adapter_for(runtime: Runtime) -> RuntimeAdapter:
    """Build the adapter that speaks to a given runtime. Raises for unknown types."""

    rtype = runtime.runtime_type
    if rtype == RuntimeType.ECHO.value:
        return EchoProvider()
    if rtype == RuntimeType.OLLAMA.value:
        return OllamaProvider(runtime.endpoint or get_settings().ollama_url)
    if rtype in _OPENAI_COMPAT_TYPES:
        # OpenAI itself has a fixed endpoint; a self-hosted server needs one.
        defaults = {
            RuntimeType.OPENAI.value: "https://api.openai.com",
            RuntimeType.DEEPSEEK.value: "https://api.deepseek.com",
        }
        endpoint = runtime.endpoint or defaults.get(rtype)
        if not endpoint:
            raise ValueError(f"runtime '{runtime.name}' has no endpoint")
        return OpenAICompatAdapter(
            endpoint, name=runtime.name, api_key=_runtime_api_key(runtime.api_key)
        )
    if rtype == RuntimeType.ANTHROPIC.value:
        return AnthropicAdapter(
            _runtime_api_key(runtime.api_key),
            base_url=runtime.endpoint or "https://api.anthropic.com",
            name=runtime.name,
        )
    raise ValueError(f"unsupported runtime_type: {rtype}")


def _runtime_api_key(stored: str | None) -> str | None:
    """Decrypt credentials written by runtime_service; accept legacy plaintext."""
    if not stored or not stored.startswith("enc:v1:"):
        return stored
    from app.services.secret_service import decrypt

    try:
        return decrypt(stored.removeprefix("enc:v1:"))
    except Exception:  # invalid/rotated master key: health reports DOWN, never leak it
        logger.exception("could not decrypt runtime credential")
        return None


def is_cloud(runtime_type: str) -> bool:
    return runtime_type in CLOUD_RUNTIME_TYPES


# --------------------------------------------------------------------------- #
# Pure helpers (unit-tested without a DB).
# --------------------------------------------------------------------------- #
def model_capabilities(model: LLMModel | None) -> set[str]:
    caps = model.capabilities if model else None
    if not caps:
        return set()
    if isinstance(caps, dict):
        return {str(k).upper() for k, v in caps.items() if v}
    if isinstance(caps, list | tuple | set):
        return {str(c).upper() for c in caps}
    return set()


def capabilities_ok(model: LLMModel | None, required: set[str]) -> bool:
    if not required:
        return True
    return required.issubset(model_capabilities(model))


def privacy_allows(runtime_type: str, privacy: str, *, cloud_allowed: bool) -> bool:
    cloud = is_cloud(runtime_type)
    if privacy == Privacy.LOCAL_ONLY:
        return not cloud
    if privacy == Privacy.CLOUD_REQUIRED:
        return cloud
    # LOCAL_PREFERRED / CLOUD_ALLOWED: cloud only if globally enabled.
    return True if not cloud else cloud_allowed


def score_candidate(
    deployment: ModelDeployment,
    runtime: Runtime,
    model: LLMModel | None,
    *,
    required: set[str],
    local_first: bool,
    runtime_priority: list[str],
    alias_rank: int | None = None,
    ordinal: int = 0,
    quality: float = 0.0,
) -> float:
    """Higher is better. Deterministic and side-effect free."""

    score = 0.0
    # Capability fit: every extra matched capability is a small plus.
    score += 5.0 * len(required & model_capabilities(model))
    # Measured quality from evals (M10): 0..1 -> up to +20.
    score += 20.0 * max(0.0, min(quality, 1.0))
    # Operator-set deployment priority dominates.
    score += float(deployment.priority)
    # Runtime-type preference (soft): earlier in the list scores higher.
    if runtime.runtime_type in runtime_priority:
        score += 10.0 * (len(runtime_priority) - runtime_priority.index(runtime.runtime_type))
    # Prefer local (non-cloud) inference.
    if local_first and not is_cloud(runtime.runtime_type):
        score += 25.0
    # Measured throughput, when we have benchmarked it (Fase 2 fills this in).
    if deployment.estimated_tokens_per_second:
        score += min(deployment.estimated_tokens_per_second, 100.0) * 0.5
    # Prefer an already-warm model — no load latency (Fase 4, concept §17/§18).
    if deployment.load_policy in ("ALWAYS_LOADED", "PINNED") or deployment.loaded:
        score += 8.0
    # An explicit alias order selects the model: it dominates every other term,
    # so a lower-ranked model never beats a higher-ranked one on priority alone.
    # Within one aliased model, the remaining terms pick the best deployment.
    if alias_rank is not None:
        score += (1000 - alias_rank) * 1_000_000.0
    # TODO(Fase 2): - current_load, + free_vram, + node latency (needs telemetry).
    # Stable tie-break: earlier-registered deployment wins.
    score -= 0.001 * ordinal
    return score


@dataclass
class _Candidate:
    deployment: ModelDeployment
    runtime: Runtime
    model: LLMModel | None
    score: float


async def _load_models_by_key(session: AsyncSession) -> dict[str, LLMModel]:
    rows = (await session.execute(select(LLMModel))).scalars().all()
    by_key: dict[str, LLMModel] = {}
    for m in rows:
        if m.model_key:
            by_key.setdefault(m.model_key, m)
    return by_key


async def _alias_targets(session: AsyncSession, alias: str) -> list[str]:
    row = (
        await session.execute(select(ModelAlias).where(ModelAlias.alias == alias))
    ).scalar_one_or_none()
    if row is None or not row.enabled or not row.targets:
        return []
    return [str(t) for t in row.targets]


async def has_deployments(session: AsyncSession) -> bool:
    """Whether any enabled deployment exists (gates the new routing path)."""

    row = (
        await session.execute(
            select(ModelDeployment.id).where(ModelDeployment.enabled.is_(True)).limit(1)
        )
    ).first()
    return row is not None


async def build_candidates(
    session: AsyncSession,
    *,
    required: set[str],
    privacy: str,
    alias: str | None = None,
    model_key: str | None = None,
) -> list[_Candidate]:
    settings = get_settings()
    models = await _load_models_by_key(session)
    runtimes = {r.id: r for r in (await session.execute(select(Runtime))).scalars().all()}
    alias_order = await _alias_targets(session, alias) if alias else []
    # Measured quality per model (M10). Best-effort: no evals -> no effect.
    try:
        from app.services import learning_service

        quality_map = await learning_service.model_quality(session)
    except Exception:  # noqa: BLE001 - routing must not depend on evals being present
        quality_map = {}

    deployments = (
        (await session.execute(select(ModelDeployment).where(ModelDeployment.enabled.is_(True))))
        .scalars()
        .all()
    )
    candidates: list[_Candidate] = []
    for ordinal, dep in enumerate(deployments):
        runtime = runtimes.get(dep.runtime_id)
        if runtime is None or not runtime.enabled:
            continue
        if not privacy_allows(
            runtime.runtime_type, privacy, cloud_allowed=settings.routing_cloud_allowed
        ):
            continue
        if model_key and dep.model_key != model_key:
            continue
        if alias_order and dep.model_key not in alias_order:
            continue
        model = models.get(dep.model_key)
        if not capabilities_ok(model, required):
            continue
        alias_rank = alias_order.index(dep.model_key) if alias_order else None
        score = score_candidate(
            dep,
            runtime,
            model,
            required=required,
            local_first=settings.routing_local_first,
            runtime_priority=settings.runtime_priority,
            alias_rank=alias_rank,
            ordinal=ordinal,
            quality=quality_map.get(dep.model_key, 0.0),
        )
        candidates.append(_Candidate(dep, runtime, model, score))

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates


async def resolve(
    session: AsyncSession,
    *,
    required_capabilities: set[str] | None = None,
    privacy: str = Privacy.LOCAL_PREFERRED,
    alias: str | None = None,
    model_key: str | None = None,
) -> RoutingDecision | None:
    """Pick the best healthy deployment, or ``None`` if none qualifies.

    Tries candidates in score order and skips any whose runtime is DOWN — that is
    the automatic fallback (§28): a stopped runtime is routed around transparently.
    """

    required = {c.upper() for c in (required_capabilities or set())}
    candidates = await build_candidates(
        session, required=required, privacy=privacy, alias=alias, model_key=model_key
    )
    for cand in candidates:
        # Skip runtimes whose circuit breaker is open (Fase 2).
        if await circuit.is_open(cand.runtime.name):
            logger.info(
                "runtime circuit open, skipping",
                extra={"event": "gateway_skip", "context": {"runtime": cand.runtime.name}},
            )
            continue
        # Skip deployments already at their concurrency limit (Fase 4).
        active = await reservation.active(cand.deployment.id)
        if not reservation.can_admit(active, cand.deployment.max_concurrency):
            logger.info(
                "deployment at capacity, skipping",
                extra={
                    "event": "gateway_skip",
                    "context": {"deployment": cand.deployment.id, "active": active},
                },
            )
            continue
        try:
            adapter = adapter_for(cand.runtime)
        except ValueError as exc:
            logger.warning("skip runtime %s: %s", cand.runtime.name, exc)
            continue
        health = await adapter.health()
        if not health.usable:
            await circuit.record_failure(cand.runtime.name)
            logger.info(
                "runtime unhealthy, trying next candidate",
                extra={
                    "event": "gateway_skip",
                    "context": {"runtime": cand.runtime.name, "state": health.state.value},
                },
            )
            continue
        await circuit.record_success(cand.runtime.name)
        reason = (
            f"{cand.runtime.runtime_type}:{cand.deployment.runtime_model_name}"
            f" on {cand.runtime.node_id or 'control-plane'} (score {cand.score:.1f})"
        )
        logger.info(
            "gateway routed request",
            extra={
                "event": "gateway_route",
                "context": {
                    "runtime": cand.runtime.name,
                    "model": cand.deployment.runtime_model_name,
                    "node": cand.runtime.node_id,
                    "score": round(cand.score, 2),
                },
            },
        )
        return RoutingDecision(
            provider=adapter,
            model=cand.deployment.runtime_model_name,
            reason=reason,
            runtime=cand.runtime.name,
            node=cand.runtime.node_id,
            deployment_id=cand.deployment.id,
            max_concurrency=cand.deployment.max_concurrency,
            score=cand.score,
        )
    return None


async def resolve_for_task(session: AsyncSession, task_type: str) -> RoutingDecision | None:
    """Route by task type using its RoutingPolicy (Fase 3 / M9).

    Applies the policy's capabilities + privacy, tries the preferred alias, then
    each fallback alias in order — the router-level escalation chain (e.g.
    local → OpenAI → Anthropic when the policy allows cloud).
    """

    policy = (
        await session.execute(select(RoutingPolicy).where(RoutingPolicy.task_type == task_type))
    ).scalar_one_or_none()
    if policy is None or not policy.enabled:
        return await resolve(session)  # no policy -> default routing

    required = {str(c).upper() for c in (policy.required_capabilities or [])}
    aliases: list[str | None] = [policy.preferred_alias]
    aliases += [str(a) for a in (policy.fallback or [])]
    for alias in aliases:
        decision = await resolve(
            session, required_capabilities=required, privacy=policy.privacy, alias=alias
        )
        if decision is not None:
            return decision
    # Last resort: any deployment satisfying the capabilities/privacy.
    return await resolve(session, required_capabilities=required, privacy=policy.privacy)
