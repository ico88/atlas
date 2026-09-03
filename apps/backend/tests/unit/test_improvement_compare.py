"""Unit tests for improvement comparison verdicts (ROADMAP PR 18)."""

from __future__ import annotations

from app.services.improvement_service import compare_metrics


def test_quality_gain_is_improvement():
    base = {"pass_rate": 0.5, "avg_quality": 0.6, "avg_safety": 1.0}
    cand = {"pass_rate": 0.7, "avg_quality": 0.8, "avg_safety": 1.0}
    out = compare_metrics(base, cand)
    assert out["verdict"] == "improvement"
    assert out["deltas"]["avg_quality"] == 0.2


def test_safety_drop_is_regression_even_if_quality_up():
    base = {"pass_rate": 0.5, "avg_quality": 0.6, "avg_safety": 1.0}
    cand = {"pass_rate": 0.9, "avg_quality": 0.9, "avg_safety": 0.8}
    assert compare_metrics(base, cand)["verdict"] == "regression"


def test_quality_drop_is_regression():
    base = {"pass_rate": 0.8, "avg_quality": 0.8, "avg_safety": 1.0}
    cand = {"pass_rate": 0.6, "avg_quality": 0.6, "avg_safety": 1.0}
    assert compare_metrics(base, cand)["verdict"] == "regression"


def test_identical_metrics_are_neutral():
    m = {"pass_rate": 0.7, "avg_quality": 0.7, "avg_safety": 1.0}
    assert compare_metrics(dict(m), dict(m))["verdict"] == "neutral"


def test_missing_metrics_are_inconclusive():
    assert compare_metrics({}, {})["verdict"] == "inconclusive"


def test_latency_only_change_is_neutral():
    base = {"pass_rate": 0.7, "avg_quality": 0.7, "avg_safety": 1.0, "p95_latency_ms": 200}
    cand = {"pass_rate": 0.7, "avg_quality": 0.7, "avg_safety": 1.0, "p95_latency_ms": 100}
    out = compare_metrics(base, cand)
    assert out["verdict"] == "neutral"
    assert out["deltas"]["p95_latency_ms"] == -100
