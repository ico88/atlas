"""Eval tests (ROADMAP PR 16): scoring, suite run, aggregation, API."""

from __future__ import annotations

import pytest
from app.services import eval_service


# --------------------------------------------------------------------------- #
# pure scoring
# --------------------------------------------------------------------------- #
def test_score_all_expected_present_passes():
    s = eval_service.score_output("The capital is Rome.", ["rome"], [])
    assert s.quality == 1.0
    assert s.safety == 1.0
    assert s.passed is True


def test_score_partial_expected():
    s = eval_service.score_output("only one here", ["one", "two"], [])
    assert s.quality == 0.5
    assert s.passed is False


def test_score_forbidden_fails_safety():
    s = eval_service.score_output("here is a password leak", ["password"], ["leak"])
    assert s.safety == 0.0
    assert s.passed is False


def test_score_no_expected_uses_nonempty():
    assert eval_service.score_output("something", None, None).quality == 1.0
    assert eval_service.score_output("", None, None).quality == 0.0


# --------------------------------------------------------------------------- #
# runner (offline echo provider)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_run_suite_scores_against_echo(session):
    suite = await eval_service.create_suite(session, name="smoke")
    # The echo provider echoes the input, so expecting the input passes.
    await eval_service.add_case(session, suite_id=suite.id, input="hello atlas",
                               expected_substrings=["hello atlas"])
    await eval_service.add_case(session, suite_id=suite.id, input="banana",
                               expected_substrings=["banana"])

    run = await eval_service.run_suite(session, suite.id)
    assert run.status == "COMPLETED"
    assert run.metrics["cases"] == 2
    assert run.metrics["pass_rate"] == 1.0
    assert run.metrics["avg_quality"] == 1.0
    assert run.provider == "echo"


@pytest.mark.asyncio
async def test_run_suite_detects_failure(session):
    suite = await eval_service.create_suite(session, name="fail-suite")
    await eval_service.add_case(session, suite_id=suite.id, input="hi",
                               expected_substrings=["this will not appear zzz"])
    run = await eval_service.run_suite(session, suite.id)
    assert run.metrics["pass_rate"] == 0.0


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_eval_api_flow(client):
    suite = await client.post("/api/v1/evals/suites", json={"name": "api-suite"})
    assert suite.status_code == 201
    sid = suite.json()["id"]

    case = await client.post(
        f"/api/v1/evals/suites/{sid}/cases",
        json={"input": "say hello", "expected_substrings": ["say hello"]},
    )
    assert case.status_code == 201

    run = await client.post(f"/api/v1/evals/suites/{sid}/run", json={"is_baseline": True})
    assert run.status_code == 201
    run_id = run.json()["id"]
    assert run.json()["status"] == "COMPLETED"
    assert run.json()["is_baseline"] is True

    detail = await client.get(f"/api/v1/evals/runs/{run_id}")
    assert detail.status_code == 200
    assert len(detail.json()["results"]) == 1
    assert detail.json()["metrics"]["pass_rate"] == 1.0

    runs = await client.get(f"/api/v1/evals/suites/{sid}/runs")
    assert runs.json()["total"] == 1


@pytest.mark.asyncio
async def test_run_unknown_suite_404(client):
    resp = await client.post("/api/v1/evals/suites/nope/run", json={})
    assert resp.status_code == 404
