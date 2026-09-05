"""Critical Review pipeline (ROADMAP PR 19).

A prompt is answered by a **proposer**, then examined by a **critic** (flaws), a
**verifier** (claims vs. references) and a **judge** (score + decision), across up
to N rounds; the best candidate wins by **adaptive consensus** (stop early once a
round clears the accept threshold).

The scoring is pure and offline-testable; only the proposer touches a model (the
echo provider when offline), so the whole pipeline runs hermetically.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import router
from app.ai.base import ChatMessage
from app.core.config import get_settings
from app.models.review import CriticalReview, ReviewDecision

logger = logging.getLogger(__name__)

_SEVERITY_WEIGHT = {"severe": 1.0, "major": 0.4, "minor": 0.2, "note": 0.1}

_HEDGING = ("non sono sicuro", "non lo so", "i'm not sure", "i am not sure", "not certain")
_REFUSAL = (
    "non posso aiutarti",
    "come intelligenza artificiale",
    "as an ai",
    "as an ai language model",
    "i cannot help",
    "i can't help",
)


# --------------------------------------------------------------------------- #
# pure roles
# --------------------------------------------------------------------------- #
def critic_findings(text: str, *, min_chars: int = 40) -> list[dict[str, Any]]:
    """Heuristic critique of a candidate answer (no model needed)."""

    findings: list[dict[str, Any]] = []
    body = (text or "").strip()
    low = body.lower()
    if not body:
        findings.append({"role": "critic", "severity": "severe", "code": "empty",
                         "message": "The answer is empty."})
        return findings
    if len(body) < min_chars:
        findings.append({"role": "critic", "severity": "minor", "code": "thin",
                         "message": f"Very short answer ({len(body)} chars)."})
    if any(p in low for p in _REFUSAL):
        findings.append({"role": "critic", "severity": "major", "code": "refusal",
                         "message": "The answer refuses or deflects."})
    if any(p in low for p in _HEDGING):
        findings.append({"role": "critic", "severity": "note", "code": "hedging",
                         "message": "The answer hedges / expresses low confidence."})
    return findings


def verify_claims(text: str, references: list[str] | None) -> dict[str, Any]:
    """Verify a candidate against reference facts (substring grounding)."""

    refs = [r for r in (references or []) if r and r.strip()]
    if not refs:
        return {"grounding": None, "supported": [], "unsupported": []}
    low = (text or "").lower()
    supported = [r for r in refs if r.lower() in low]
    unsupported = [r for r in refs if r.lower() not in low]
    grounding = round(len(supported) / len(refs), 4)
    return {"grounding": grounding, "supported": supported, "unsupported": unsupported}


def judge(
    findings: list[dict[str, Any]],
    verification: dict[str, Any],
    *,
    accept: float = 0.8,
    revise: float = 0.5,
) -> dict[str, Any]:
    """Combine critic + verifier into a score and a decision."""

    penalty = sum(_SEVERITY_WEIGHT.get(f.get("severity", "note"), 0.1) for f in findings)
    quality = max(0.0, 1.0 - penalty)
    grounding = verification.get("grounding")
    score = quality if grounding is None else round(0.5 * quality + 0.5 * grounding, 4)

    if score >= accept:
        decision = ReviewDecision.ACCEPT.value
    elif score >= revise:
        decision = ReviewDecision.REVISE.value
    else:
        decision = ReviewDecision.REJECT.value

    reasons = [f["message"] for f in findings]
    if verification.get("unsupported"):
        reasons.append(
            "Unsupported claims: " + ", ".join(verification["unsupported"][:5])
        )
    return {"score": round(score, 4), "decision": decision, "reasons": reasons}


def consensus(rounds: list[dict[str, Any]]) -> dict[str, Any]:
    """Pick the best round and report agreement across rounds."""

    if not rounds:
        return {"best_index": -1, "agreement": 0.0, "rounds": 0}
    best_index = max(range(len(rounds)), key=lambda i: rounds[i]["score"])
    best_decision = rounds[best_index]["decision"]
    agree = sum(1 for r in rounds if r["decision"] == best_decision) / len(rounds)
    return {"best_index": best_index, "agreement": round(agree, 4), "rounds": len(rounds)}


# --------------------------------------------------------------------------- #
# proposer + orchestration
# --------------------------------------------------------------------------- #
async def _propose(prompt: str, attempt: int, model: str | None) -> tuple[str, str, str]:
    """Generate one candidate answer. Returns (text, provider, model)."""

    system = (
        "You are a careful expert. Answer accurately and concisely. "
        "If unsure, say what is uncertain."
    )
    if attempt > 0:
        system += f" This is revision attempt {attempt + 1}; improve on prior answers."
    decision = await router.select(requested_model=model)
    parts: list[str] = []
    async for piece in decision.provider.stream_chat(
        [ChatMessage(role="system", content=system), ChatMessage(role="user", content=prompt)],
        decision.model,
    ):
        parts.append(piece)
    return "".join(parts).strip(), decision.provider.name, decision.model


async def run_review(
    session: AsyncSession,
    *,
    prompt: str,
    references: list[str] | None = None,
    max_rounds: int | None = None,
    model: str | None = None,
) -> CriticalReview:
    """Run the critical-review pipeline and persist the result."""

    settings = get_settings()
    max_rounds = max_rounds or settings.review_max_rounds
    accept = settings.review_accept_threshold
    revise = settings.review_revise_threshold

    rounds: list[dict[str, Any]] = []
    provider_name: str | None = None
    used_model: str | None = None
    started = time.perf_counter()

    for i in range(max(1, max_rounds)):
        answer, provider_name, used_model = await _propose(prompt, i, model)
        findings = critic_findings(answer, min_chars=settings.review_min_answer_chars)
        verification = verify_claims(answer, references)
        verdict = judge(findings, verification, accept=accept, revise=revise)
        rounds.append(
            {
                "attempt": i + 1,
                "answer": answer,
                "findings": findings,
                "verification": verification,
                "score": verdict["score"],
                "decision": verdict["decision"],
                "reasons": verdict["reasons"],
            }
        )
        if verdict["score"] >= accept:
            break  # adaptive: good enough, stop early

    cons = consensus(rounds)
    best = rounds[cons["best_index"]]
    review = CriticalReview(
        prompt=prompt,
        references=references or None,
        best_answer=best["answer"],
        best_score=best["score"],
        decision=best["decision"],
        rounds=rounds,
        consensus=cons,
        provider=provider_name,
        model=used_model or model,
        round_count=len(rounds),
    )
    session.add(review)
    await session.commit()
    await session.refresh(review)
    logger.info(
        "critical review done",
        extra={
            "event": "review_done",
            "context": {
                "decision": review.decision,
                "score": review.best_score,
                "rounds": len(rounds),
                "ms": int((time.perf_counter() - started) * 1000),
            },
        },
    )
    return review


async def list_reviews(session: AsyncSession, *, limit: int = 50) -> list[CriticalReview]:
    result = await session.execute(
        select(CriticalReview).order_by(CriticalReview.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def get_review(session: AsyncSession, review_id: str) -> CriticalReview | None:
    return await session.get(CriticalReview, review_id)
