"""Unit tests for fleet compliance drift + diagnosis (ROADMAP PR 24 / PR 25)."""

from __future__ import annotations

from app.services.compliance_service import compute_drift
from app.services.remediation_service import diagnose


def _n(ref, online=True, version="1.0.0", caps=None, quar=False):
    return {
        "ref": ref,
        "online": online,
        "version": version,
        "capabilities": caps or ["build"],
        "quarantined": quar,
    }


def test_all_compliant():
    desired = {"target_version": "1.0.0", "required_capabilities": ["build"], "min_online": 1}
    out = compute_drift([_n("a")], desired)
    assert out["summary"]["compliant"] == 1
    assert out["summary"]["compliance_pct"] == 1.0
    assert out["summary"]["meets_min_online"] is True
    assert out["nodes"][0]["compliant"] is True


def test_version_and_capability_drift_flagged():
    desired = {
        "target_version": "2.0.0",
        "required_capabilities": ["build", "gpu"],
        "min_online": 2,
    }
    out = compute_drift([_n("a", version="1.0.0")], desired)
    node = out["nodes"][0]
    assert node["compliant"] is False
    assert any("version" in i for i in node["issues"])
    assert any("missing capability" in i for i in node["issues"])
    assert out["summary"]["meets_min_online"] is False  # only 1 online, need 2


def test_offline_and_quarantine_counted():
    desired = {"target_version": "1.0.0", "required_capabilities": [], "min_online": 0}
    out = compute_drift(
        [_n("a", online=False), _n("b", quar=True)], desired
    )
    s = out["summary"]
    assert s["online"] == 1 and s["quarantined"] == 1 and s["compliant"] == 0


def test_diagnose_recommendations():
    # version drift -> auto remediate
    dx = diagnose({"issues": ["version 1 != 2"], "compliant": False, "quarantined": False})
    assert dx["recommended_action"] == "remediate" and dx["auto"] is True
    # offline -> quarantine (manual)
    dx = diagnose({"issues": ["offline"], "compliant": False, "quarantined": False})
    assert dx["recommended_action"] == "quarantine" and dx["auto"] is False
    # quarantined -> reinstate
    dx = diagnose({"issues": ["quarantined"], "compliant": False, "quarantined": True})
    assert dx["recommended_action"] == "reinstate"
