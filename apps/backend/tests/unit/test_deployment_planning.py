"""Unit tests for fleet deployment planning (ROADMAP PR 21)."""

from __future__ import annotations

from app.services.deployment_service import is_compatible, plan_targets, version_tuple


def _n(pk, online=True, version="1.0.0"):
    return {"pk": pk, "ref": f"node-{pk}", "version": version, "online": online}


def test_version_tuple_and_compat():
    assert version_tuple("v1.2.3") == (1, 2, 3)
    assert is_compatible("1.2.0", "1.0.0") is True
    assert is_compatible("0.9.0", "1.0.0") is False
    assert is_compatible(None, "1.0.0") is True  # unknown version allowed
    assert is_compatible("0.1", None) is True  # no floor


def test_plan_splits_canary_and_rollout():
    nodes = [_n("a"), _n("b"), _n("c"), _n("d")]
    plans = plan_targets(nodes, canary_count=1)
    by_ref = {p.node_ref: p for p in plans}
    assert by_ref["node-a"].wave == "canary"
    assert by_ref["node-b"].wave == "rollout"
    assert all(p.status == "PENDING" for p in plans)


def test_plan_skips_offline_and_incompatible():
    nodes = [_n("a", online=False), _n("b", version="0.1.0"), _n("c")]
    plans = {p.node_ref: p for p in plan_targets(nodes, canary_count=1, min_compatible="1.0.0")}
    assert plans["node-a"].status == "SKIPPED_OFFLINE"
    assert plans["node-b"].status == "INCOMPATIBLE"
    assert plans["node-c"].wave == "canary" and plans["node-c"].status == "PENDING"
