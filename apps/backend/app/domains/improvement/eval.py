"""Evaluation service (ROADMAP PR 16): scoring + suite runner.

Scoring is pure and offline-testable. A run executes each case through the AI
router (echo provider offline) and aggregates quality / safety / performance.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai import router
from app.ai.base import ChatMessage
from app.models.base import utcnow
from app.models.eval import EvalCase, EvalResult, EvalRun, EvalRunStatus, EvalSuite

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# pure scoring
# --------------------------------------------------------------------------- #
@dataclass
class CaseScore:
    quality: float
    safety: float
    passed: bool


def score_output(
    output: str,
    expected: list[str] | None,
    forbidden: list[str] | None,
) -> CaseScore:
    """Score one output. quality = fraction of expected present; safety = no forbidden."""

    low = (output or "").lower()
    expected = expected or []
    forbidden = forbidden or []

    if expected:
        hits = sum(1 for s in expected if s.lower() in low)
        quality = round(hits / len(expected), 4)
    else:
        quality = 1.0 if low.strip() else 0.0

    violated = any(s.lower() in low for s in forbidden)
    safety = 0.0 if violated else 1.0
    passed = quality >= 1.0 and safety >= 1.0
    return CaseScore(quality=quality, safety=safety, passed=passed)


def aggregate(results: list[EvalResult]) -> dict[str, Any]:
    n = len(results)
    if n == 0:
        return {"cases": 0, "pass_rate": 0.0, "avg_quality": 0.0, "avg_safety": 1.0}
    latencies = sorted(r.latency_ms for r in results if r.latency_ms is not None)
    p95 = latencies[int(0.95 * (len(latencies) - 1))] if latencies else None
    return {
        "cases": n,
        "passed": sum(1 for r in results if r.passed),
        "pass_rate": round(sum(1 for r in results if r.passed) / n, 4),
        "avg_quality": round(sum(r.quality for r in results) / n, 4),
        "avg_safety": round(sum(r.safety for r in results) / n, 4),
        "avg_latency_ms": round(sum(latencies) / len(latencies)) if latencies else None,
        "p95_latency_ms": p95,
    }


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #
async def create_suite(
    session: AsyncSession, *, name: str, description: str | None = None
) -> EvalSuite:
    suite = EvalSuite(name=name, description=description)
    session.add(suite)
    await session.commit()
    await session.refresh(suite)
    return suite


async def add_case(
    session: AsyncSession,
    *,
    suite_id: str,
    input: str,
    expected_substrings: list[str] | None = None,
    forbidden_substrings: list[str] | None = None,
    category: str = "quality",
) -> EvalCase:
    case = EvalCase(
        suite_id=suite_id,
        input=input,
        expected_substrings=expected_substrings,
        forbidden_substrings=forbidden_substrings,
        category=category,
    )
    session.add(case)
    await session.commit()
    await session.refresh(case)
    return case


async def list_suites(session: AsyncSession) -> list[EvalSuite]:
    return list(
        (
            await session.execute(select(EvalSuite).order_by(EvalSuite.created_at.desc()))
        )
        .scalars()
        .all()
    )


async def get_suite(session: AsyncSession, suite_id: str) -> EvalSuite | None:
    result = await session.execute(
        select(EvalSuite).where(EvalSuite.id == suite_id).options(selectinload(EvalSuite.cases))
    )
    return result.scalar_one_or_none()


async def get_run(session: AsyncSession, run_id: str) -> EvalRun | None:
    result = await session.execute(
        select(EvalRun).where(EvalRun.id == run_id).options(selectinload(EvalRun.results))
    )
    return result.scalar_one_or_none()


async def list_runs(session: AsyncSession, suite_id: str) -> list[EvalRun]:
    return list(
        (
            await session.execute(
                select(EvalRun)
                .where(EvalRun.suite_id == suite_id)
                .order_by(EvalRun.created_at.desc())
            )
        )
        .scalars()
        .all()
    )


# --------------------------------------------------------------------------- #
# runner
# --------------------------------------------------------------------------- #
async def _generate(prompt: str, model: str | None) -> tuple[str, str, str, int]:
    """Run one prompt through the router. Returns (output, provider, model, latency_ms)."""

    decision = await router.select(requested_model=model)
    started = time.perf_counter()
    parts: list[str] = []
    async for piece in decision.provider.stream_chat(
        [ChatMessage(role="user", content=prompt)], decision.model
    ):
        parts.append(piece)
    latency = int((time.perf_counter() - started) * 1000)
    return "".join(parts), decision.provider.name, decision.model, latency


async def run_suite(
    session: AsyncSession, suite_id: str, *, model: str | None = None, is_baseline: bool = False
) -> EvalRun:
    """Execute every case in a suite and persist per-case results + aggregate metrics."""

    suite = await get_suite(session, suite_id)
    if suite is None:
        raise ValueError("suite not found")

    run = EvalRun(
        suite_id=suite_id,
        model=model,
        status=EvalRunStatus.RUNNING.value,
        is_baseline=is_baseline,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    results: list[EvalResult] = []
    provider_name = None
    used_model = None
    try:
        for case in suite.cases:
            output, provider_name, used_model, latency = await _generate(case.input, model)
            score = score_output(output, case.expected_substrings, case.forbidden_substrings)
            result = EvalResult(
                run_id=run.id,
                case_id=case.id,
                output=output,
                passed=score.passed,
                quality=score.quality,
                safety=score.safety,
                latency_ms=latency,
            )
            session.add(result)
            results.append(result)
        run.provider = provider_name
        run.model = used_model or model
        run.metrics = aggregate(results)
        run.status = EvalRunStatus.COMPLETED.value
        run.completed_at = utcnow()
    except Exception as exc:  # noqa: BLE001 - persist failure state
        logger.exception("eval run failed")
        run.status = EvalRunStatus.FAILED.value
        run.metrics = {"error": str(exc)}
        run.completed_at = utcnow()
    await session.commit()
    await session.refresh(run)
    logger.info(
        "eval run finished",
        extra={"event": "eval_run", "context": {"suite": suite.name, "status": run.status}},
    )
    return run
