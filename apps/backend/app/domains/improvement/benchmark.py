"""Deployment benchmarking (multi-runtime Fase 2).

Measures a deployment's real throughput (tokens/sec) and first-token latency by
streaming a short prompt through its runtime adapter, then persists the result on
the deployment so the Model Gateway's score reflects measured performance rather
than a guess. The same model benchmarked on a different node/runtime yields a
different number — which is exactly the point.
"""

from __future__ import annotations

import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import gateway
from app.ai.base import ChatMessage
from app.core.config import get_settings
from app.models.base import utcnow
from app.models.runtime import ModelDeployment, Runtime

logger = logging.getLogger(__name__)

_PROMPT = "In one short sentence, say hello and confirm you are working."


async def benchmark_deployment(
    session: AsyncSession, deployment: ModelDeployment, runtime: Runtime
) -> dict:
    """Run one timed generation and store tokens/sec on the deployment.

    Never raises: an unreachable runtime yields ``ok=False`` and leaves the
    stored benchmark untouched.
    """

    settings = get_settings()
    max_tokens = settings.runtime_benchmark_max_tokens
    try:
        adapter = gateway.adapter_for(runtime)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    messages = [ChatMessage(role="user", content=_PROMPT)]
    start = time.monotonic()
    first_token_at: float | None = None
    chunks = 0
    try:
        async for piece in adapter.stream_chat(messages, deployment.runtime_model_name):
            if not piece:
                continue
            if first_token_at is None:
                first_token_at = time.monotonic()
            chunks += 1
            if chunks >= max_tokens:
                break
    except Exception as exc:  # noqa: BLE001 - benchmarking must never crash the caller
        logger.warning("benchmark failed for %s: %s", runtime.name, exc)
        return {"ok": False, "error": str(exc)}

    elapsed = max(time.monotonic() - start, 1e-6)
    tps = round(chunks / elapsed, 2) if chunks else 0.0
    ttft_ms = round((first_token_at - start) * 1000, 1) if first_token_at else None

    deployment.estimated_tokens_per_second = tps
    deployment.last_benchmark = utcnow()
    await session.commit()
    await session.refresh(deployment)
    logger.info(
        "deployment benchmarked",
        extra={
            "event": "benchmark",
            "context": {
                "runtime": runtime.name,
                "model": deployment.runtime_model_name,
                "tokens_per_second": tps,
            },
        },
    )
    return {
        "ok": True,
        "tokens": chunks,
        "tokens_per_second": tps,
        "first_token_ms": ttft_ms,
        "elapsed_ms": round(elapsed * 1000, 1),
    }
