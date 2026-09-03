"""Integration tests for the Maintenance Agent workflow (M6)."""

from __future__ import annotations

import pytest

LOG = {
    "message": "ollama_timeout while generating response after 30s",
    "service": "backend",
    "level": "ERROR",
    "event": "ollama_timeout",
}


@pytest.mark.asyncio
async def test_ingest_dedups_by_fingerprint(client):
    first = await client.post("/api/v1/maintenance/logs", json=LOG)
    assert first.status_code == 201
    # Same error, different duration -> same issue, occurrences incremented.
    second = await client.post(
        "/api/v1/maintenance/logs",
        json={**LOG, "message": "ollama_timeout while generating response after 5s"},
    )
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    issues = await client.get("/api/v1/maintenance/issues")
    assert issues.json()["total"] == 1
    assert issues.json()["items"][0]["occurrences"] == 2
    assert issues.json()["items"][0]["severity"] == "high"  # ERROR


@pytest.mark.asyncio
async def test_full_fix_flow_with_approval_gate(client):
    issue_id = (await client.post("/api/v1/maintenance/logs", json=LOG)).json()["id"]

    analyzed = await client.post(f"/api/v1/maintenance/issues/{issue_id}/analyze")
    assert analyzed.status_code == 200
    assert analyzed.json()["status"] == "ANALYZED"

    fixed = await client.post(f"/api/v1/maintenance/issues/{issue_id}/create-fix")
    assert fixed.status_code == 200
    run = fixed.json()
    assert run["status"] == "NEEDS_APPROVAL"
    assert run["branch"].startswith("maintenance/")
    assert run["branch"] not in ("main", "master")
    assert run["pr_url"]

    # Issue is now awaiting human approval.
    detail = (await client.get(f"/api/v1/maintenance/issues/{issue_id}")).json()
    assert detail["status"] == "FIX_PROPOSED"

    # A pending approval gate was created (spec §11 step 12).
    approvals = (await client.get("/api/v1/approvals?status=PENDING")).json()
    assert approvals["total"] == 1
    approval_id = approvals["items"][0]["id"]
    assert approvals["items"][0]["subject_type"] == "maintenance_run"

    # Approve it -> issue resolved.
    approved = await client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        json={"decided_by": "alice"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["decided_by"] == "alice"

    detail = (await client.get(f"/api/v1/maintenance/issues/{issue_id}")).json()
    assert detail["status"] == "RESOLVED"


@pytest.mark.asyncio
async def test_reject_reopens_issue(client):
    issue_id = (await client.post("/api/v1/maintenance/logs", json=LOG)).json()["id"]
    await client.post(f"/api/v1/maintenance/issues/{issue_id}/create-fix")
    approval_id = (await client.get("/api/v1/approvals?status=PENDING")).json()["items"][0]["id"]

    rejected = await client.post(
        f"/api/v1/approvals/{approval_id}/reject", json={"decided_by": "bob"}
    )
    assert rejected.json()["status"] == "REJECTED"

    detail = (await client.get(f"/api/v1/maintenance/issues/{issue_id}")).json()
    assert detail["status"] == "OPEN"


@pytest.mark.asyncio
async def test_double_decision_conflicts(client):
    issue_id = (await client.post("/api/v1/maintenance/logs", json=LOG)).json()["id"]
    await client.post(f"/api/v1/maintenance/issues/{issue_id}/create-fix")
    approval_id = (await client.get("/api/v1/approvals?status=PENDING")).json()["items"][0]["id"]

    await client.post(f"/api/v1/approvals/{approval_id}/approve", json={})
    again = await client.post(f"/api/v1/approvals/{approval_id}/approve", json={})
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_create_fix_validates_in_real_sandbox(client):
    issue_id = (await client.post("/api/v1/maintenance/logs", json=LOG)).json()["id"]
    fixed = (await client.post(f"/api/v1/maintenance/issues/{issue_id}/create-fix")).json()

    # The recorded patch is a real unified diff and the sandbox actually ran.
    assert fixed["patch"].startswith("--- a/")
    assert "@@" in fixed["patch"]
    assert "applies cleanly" in (fixed["tests_summary"] or "")


@pytest.mark.asyncio
async def test_apply_fix_requires_approval_then_opens_pr(client):
    issue_id = (await client.post("/api/v1/maintenance/logs", json=LOG)).json()["id"]
    await client.post(f"/api/v1/maintenance/issues/{issue_id}/create-fix")

    # Applying before approval is refused (governance gate).
    early = await client.post(f"/api/v1/maintenance/issues/{issue_id}/apply-fix")
    assert early.status_code == 409

    approval_id = (await client.get("/api/v1/approvals?status=PENDING")).json()["items"][0]["id"]
    await client.post(f"/api/v1/approvals/{approval_id}/approve", json={"decided_by": "alice"})

    # After approval the governed apply opens the (dry-run) PR.
    applied = await client.post(f"/api/v1/maintenance/issues/{issue_id}/apply-fix")
    assert applied.status_code == 200
    run = applied.json()
    assert run["status"] == "PR_OPENED"
    assert run["pr_url"]


@pytest.mark.asyncio
async def test_sandbox_endpoint_applies_patch(client):
    before = "one\ntwo\nthree\n"
    patch = (
        "--- a/f.txt\n+++ b/f.txt\n@@ -1,3 +1,3 @@\n one\n-two\n+TWO\n three\n"
    )
    resp = await client.post(
        "/api/v1/maintenance/sandbox", json={"files": {"f.txt": before}, "patch": patch}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["applied"] is True
    assert body["passed"] is True
    assert body["files"] == ["f.txt"]


@pytest.mark.asyncio
async def test_sandbox_endpoint_reports_bad_patch(client):
    patch = "--- a/f.txt\n+++ b/f.txt\n@@ -1,1 +1,1 @@\n-nope\n+yep\n"
    resp = await client.post(
        "/api/v1/maintenance/sandbox", json={"files": {"f.txt": "unrelated\n"}, "patch": patch}
    )
    assert resp.status_code == 200
    assert resp.json()["applied"] is False


@pytest.mark.asyncio
async def test_create_fix_records_git_actions_within_policy(client, session):
    from app.services import maintenance_service

    issue_id = (await client.post("/api/v1/maintenance/logs", json=LOG)).json()["id"]
    await client.post(f"/api/v1/maintenance/issues/{issue_id}/create-fix")

    issue = await maintenance_service.get_issue(session, issue_id)
    run = issue.runs[-1]
    actions = await maintenance_service.list_git_actions(session, run.id)
    names = [a.action for a in actions]
    assert "create_branch" in names and "open_pr" in names
    assert all(a.allowed for a in actions)
    # Never a forbidden action on a protected branch.
    assert all(a.branch != "main" for a in actions if a.branch)
