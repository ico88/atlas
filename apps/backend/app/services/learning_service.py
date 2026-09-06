"""Adaptive routing from evals (ROADMAP M10 — optimization).

Closes the loop: the eval suite (PR 16) measures each model's quality; the Model
Gateway then prefers higher-quality models. Quality per model is the ``avg_quality``
of that model's **latest completed** eval run (0..1). Nothing here changes a model
automatically — switching the default/alias stays human-gated (see suggestions),
in keeping with ATLAS's approval philosophy; the gateway just scores smarter.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.eval import EvalRun, EvalRunStatus
from app.models.runtime import ModelAlias

logger = logging.getLogger(__name__)


async def model_quality(session: AsyncSession) -> dict[str, float]:
    """Map model name -> measured quality (latest completed run's avg_quality)."""

    rows = (
        await session.execute(
            select(EvalRun)
            .where(EvalRun.status == EvalRunStatus.COMPLETED.value, EvalRun.model.isnot(None))
            .order_by(EvalRun.completed_at.desc().nullslast(), EvalRun.created_at.desc())
        )
    ).scalars().all()
    quality: dict[str, float] = {}
    for run in rows:
        model = run.model
        if not model or model in quality:  # keep only the most recent per model
            continue
        metrics = run.metrics or {}
        val = metrics.get("avg_quality")
        if isinstance(val, int | float):
            quality[model] = float(val)
    return quality


async def alias_suggestions(session: AsyncSession) -> list[dict]:
    """Suggest re-pointing an alias to a higher-quality target (human-gated).

    For each alias, if a non-primary target has measurably higher quality than the
    current primary, propose the switch. The operator applies it, ATLAS does not.
    """

    quality = await model_quality(session)
    if not quality:
        return []
    aliases = (await session.execute(select(ModelAlias))).scalars().all()
    out: list[dict] = []
    for alias in aliases:
        targets = [str(t) for t in (alias.targets or [])]
        if len(targets) < 2:
            continue
        current = targets[0]
        scored = [(t, quality.get(t)) for t in targets if quality.get(t) is not None]
        if not scored:
            continue
        best_model, best_q = max(scored, key=lambda x: x[1] or 0.0)
        cur_q = quality.get(current, 0.0)
        # Only suggest when the improvement is meaningful (> 5 points of quality).
        if best_model != current and (best_q or 0.0) - cur_q > 0.05:
            out.append(
                {
                    "alias": alias.alias,
                    "current": current,
                    "current_quality": round(cur_q, 4),
                    "suggested": best_model,
                    "suggested_quality": round(best_q or 0.0, 4),
                }
            )
    return out
