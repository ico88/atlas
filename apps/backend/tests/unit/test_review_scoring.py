"""Unit tests for the critical-review scoring roles (ROADMAP PR 19)."""

from __future__ import annotations

from app.services.review_service import (
    consensus,
    critic_findings,
    judge,
    verify_claims,
)


def test_critic_flags_empty_and_thin():
    assert critic_findings("")[0]["code"] == "empty"
    thin = critic_findings("short", min_chars=40)
    assert any(f["code"] == "thin" for f in thin)


def test_critic_flags_refusal_and_hedging():
    f = critic_findings("As an AI, I cannot help. I'm not sure anyway.", min_chars=1)
    codes = {x["code"] for x in f}
    assert "refusal" in codes and "hedging" in codes


def test_verify_grounding():
    v = verify_claims("The capital is Rome and the year is 1861.", ["Rome", "1861", "Milan"])
    assert v["grounding"] == round(2 / 3, 4)
    assert "Milan" in v["unsupported"]


def test_verify_no_references_is_neutral():
    assert verify_claims("anything", None)["grounding"] is None


def test_judge_accepts_clean_grounded_answer():
    v = verify_claims("Rome 1861", ["Rome", "1861"])
    out = judge([], v, accept=0.8, revise=0.5)
    assert out["decision"] == "accept"
    assert out["score"] == 1.0


def test_judge_rejects_empty():
    findings = critic_findings("")
    out = judge(findings, {"grounding": None}, accept=0.8, revise=0.5)
    assert out["decision"] == "reject"
    assert out["score"] == 0.0


def test_consensus_picks_best_and_agreement():
    rounds = [
        {"score": 0.4, "decision": "reject"},
        {"score": 0.9, "decision": "accept"},
        {"score": 0.85, "decision": "accept"},
    ]
    c = consensus(rounds)
    assert c["best_index"] == 1
    assert c["agreement"] == round(2 / 3, 4)
