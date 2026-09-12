"""Code self-review: deterministic findings -> maintenance issues (propose-only)."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.maintenance import self_review as sr
from app.models.maintenance import IssueStatus, MaintenanceIssue
from app.services import code_review_service
from sqlalchemy import select


# --------------------------------------------------------------------------- #
# Pure scanners
# --------------------------------------------------------------------------- #
def test_scan_markers_detects_and_grades():
    text = "x = 1  # TODO: tidy up\n# FIXME broken path\nok = 2\n"
    found = sr.scan_markers("a.py", text)
    kinds = {(f.code, f.severity) for f in found}
    assert ("TODO", "low") in kinds
    assert ("FIXME", "medium") in kinds
    # A marker word inside a normal string (no comment char) is not flagged.
    assert sr.scan_markers("b.py", 'msg = "the todo list"\n') == []


def test_scan_long_file_threshold():
    short = "\n".join(str(i) for i in range(10))
    assert sr.scan_long_file("s.py", short, threshold=50) == []
    long_text = "\n".join(str(i) for i in range(60))
    out = sr.scan_long_file("l.py", long_text, threshold=50)
    assert len(out) == 1 and out[0].kind == "long-file"


def test_parse_ruff_json_relativizes():
    payload = [
        {
            "filename": "/repo/apps/backend/app/x.py",
            "code": "E501",
            "message": "Line too long",
            "location": {"row": 12, "column": 1},
        }
    ]
    out = sr.parse_ruff_json(payload, "/repo")
    assert out[0].path == "apps/backend/app/x.py"
    assert out[0].line == 12 and out[0].code == "E501"


def test_signature_stable_across_line_moves_and_dedups():
    a = sr.Finding(kind="marker", path="a.py", line=3, code="TODO", message="fix me")
    b = sr.Finding(kind="marker", path="a.py", line=99, code="TODO", message="fix me")
    assert a.signature() == b.signature()
    assert len(sr.dedup([a, b])) == 1


# --------------------------------------------------------------------------- #
# Service against a temp repo
# --------------------------------------------------------------------------- #
def _make_repo(tmp_path: Path) -> Path:
    src = tmp_path / "apps" / "backend" / "app"
    src.mkdir(parents=True)
    (src / "sample.py").write_text(
        "def f():\n    pass  # FIXME: needs work\n", encoding="utf-8"
    )
    return tmp_path


@pytest.mark.asyncio
async def test_scan_finds_marker(tmp_path, monkeypatch):
    root = _make_repo(tmp_path)
    monkeypatch.setattr(code_review_service, "_run_ruff", _no_ruff)
    findings, scanned = await code_review_service.scan(root)
    assert scanned == 1
    assert any(f.code == "FIXME" for f in findings)


async def _no_ruff(_root):
    return []


@pytest.mark.asyncio
async def test_run_self_review_files_issues_and_dedups(tmp_path, monkeypatch, session):
    root = _make_repo(tmp_path)
    monkeypatch.setattr(code_review_service, "_run_ruff", _no_ruff)

    first = await code_review_service.run_self_review(session, root)
    assert first["new_issues"] >= 1

    issues = (
        await session.execute(
            select(MaintenanceIssue).where(MaintenanceIssue.service == "self-review")
        )
    ).scalars().all()
    assert issues
    issue = issues[0]
    assert issue.status == IssueStatus.OPEN.value
    assert issue.sample["source"] == "self-review"

    # A second sweep adds no new issues (dedup) but bumps occurrences.
    second = await code_review_service.run_self_review(session, root)
    assert second["new_issues"] == 0
    await session.refresh(issue)
    assert issue.occurrences == 2


@pytest.mark.asyncio
async def test_scan_real_repo_root_runs(monkeypatch):
    # repo_root() derivation must point at the real tree and scan without error.
    monkeypatch.setattr(code_review_service, "_run_ruff", _no_ruff)
    findings, scanned = await code_review_service.scan()
    assert scanned > 0  # our own source is there
    assert isinstance(findings, list)


@pytest.mark.asyncio
async def test_self_review_api(client, tmp_path, monkeypatch):
    root = _make_repo(tmp_path)
    monkeypatch.setattr(code_review_service, "_run_ruff", _no_ruff)
    monkeypatch.setattr(code_review_service, "repo_root", lambda: root)
    resp = await client.post("/api/v1/maintenance/self-review")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scanned"] == 1 and body["new_issues"] >= 1
