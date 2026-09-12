"""LLM code-patch pipeline: model writes the fix, validated, awaiting approval."""

from __future__ import annotations

import pytest
from app.models.maintenance import IssueStatus, MaintenanceIssue
from app.models.provider import LLMModel
from app.services import code_patch_service, code_review_service


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def test_is_coder_model():
    assert code_patch_service.is_coder_model("qwen2.5-coder:7b")
    assert code_patch_service.is_coder_model("codellama:13b")
    assert not code_patch_service.is_coder_model("llama3.2:3b")


def test_extract_file_prefers_fenced_block():
    out = "Sure:\n```python\nx = 1\n```\ntrailing"
    assert code_patch_service.extract_file(out) == "x = 1\n"
    # Bare output (no fence) falls back to the raw text.
    assert code_patch_service.extract_file("y = 2") == "y = 2\n"
    assert code_patch_service.extract_file("") is None


def test_validate_syntax_rejects_broken_python():
    ok, _ = code_patch_service.validate_syntax("a.py", "def f(:\n    pass\n")
    assert not ok
    ok2, _ = code_patch_service.validate_syntax("a.py", "def f():\n    return 1\n")
    assert ok2
    # Non-python is not syntax-checked here.
    assert code_patch_service.validate_syntax("a.ts", "const x=;")[0]


def test_make_diff_roundtrips():
    diff = code_patch_service.make_diff("m.py", "a\nb\n", "a\nc\n")
    assert "--- a/m.py" in diff and "+++ b/m.py" in diff
    assert "-b" in diff and "+c" in diff


# --------------------------------------------------------------------------- #
# Model selection
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_select_coder_model_detects_available(session):
    assert await code_patch_service.select_coder_model(session) is None
    session.add(LLMModel(provider="ollama", name="llama3.2:3b", available=True))
    session.add(LLMModel(provider="ollama", name="qwen2.5-coder:7b", available=True))
    await session.commit()
    assert await code_patch_service.select_coder_model(session) == "qwen2.5-coder:7b"


@pytest.mark.asyncio
async def test_complete_refuses_echo(session):
    # With no real runtime, the router falls back to echo -> must refuse, not fake.
    from app.ai.base import ChatMessage

    msgs = [ChatMessage(role="user", content="x")]
    with pytest.raises(code_patch_service.CodePatchError):
        await code_patch_service.complete("qwen2.5-coder:7b", msgs)


# --------------------------------------------------------------------------- #
# End-to-end (model completion mocked)
# --------------------------------------------------------------------------- #
async def _no_ruff(_root):
    return []


async def _seed(session, tmp_path) -> MaintenanceIssue:
    from app.services import maintenance_service

    src = tmp_path / "apps" / "backend" / "app"
    src.mkdir(parents=True)
    (src / "sample.py").write_text("def f():\n    pass  # FIXME: real work\n", encoding="utf-8")
    session.add(LLMModel(provider="ollama", name="qwen2.5-coder:7b", available=True))
    await session.commit()
    await code_review_service.run_self_review(session, tmp_path)
    issues = await maintenance_service.list_issues(session)
    return await maintenance_service.get_issue(session, issues[0].id)


@pytest.mark.asyncio
async def test_propose_patch_creates_fix_awaiting_approval(session, tmp_path, monkeypatch):
    monkeypatch.setattr(code_review_service, "_run_ruff", _no_ruff)
    monkeypatch.setattr(code_review_service, "repo_root", lambda: tmp_path)
    issue = await _seed(session, tmp_path)

    async def fake_complete(model, messages):
        return "```python\ndef f():\n    return None\n```"

    monkeypatch.setattr(code_patch_service, "complete", fake_complete)

    run = await code_patch_service.propose_patch(session, issue)
    assert run.patch and "return None" in run.patch
    assert run.status == "NEEDS_APPROVAL"
    await session.refresh(issue)
    assert issue.status == IssueStatus.FIX_PROPOSED.value

    # An approval gate was opened (propose-only; nothing merged).
    from app.services import approval_service

    pend = await approval_service.list_approvals(session, status="PENDING")
    assert any(a.subject_type == "maintenance_run" for a in pend)


@pytest.mark.asyncio
async def test_propose_patch_rejects_broken_python(session, tmp_path, monkeypatch):
    monkeypatch.setattr(code_review_service, "_run_ruff", _no_ruff)
    monkeypatch.setattr(code_review_service, "repo_root", lambda: tmp_path)
    issue = await _seed(session, tmp_path)

    async def broken(model, messages):
        return "```python\ndef f(:\n    pass\n```"

    monkeypatch.setattr(code_patch_service, "complete", broken)
    with pytest.raises(code_patch_service.CodePatchError):
        await code_patch_service.propose_patch(session, issue)


@pytest.mark.asyncio
async def test_propose_patch_without_coder_model_fails(session, tmp_path, monkeypatch):
    monkeypatch.setattr(code_review_service, "_run_ruff", _no_ruff)
    monkeypatch.setattr(code_review_service, "repo_root", lambda: tmp_path)
    # Seed an issue but NO coder model.
    src = tmp_path / "apps" / "backend" / "app"
    src.mkdir(parents=True)
    (src / "s.py").write_text("x = 1  # FIXME: y\n", encoding="utf-8")
    await code_review_service.run_self_review(session, tmp_path)
    from app.services import maintenance_service

    issues = await maintenance_service.list_issues(session)
    issue = await maintenance_service.get_issue(session, issues[0].id)

    with pytest.raises(code_patch_service.CodePatchError):
        await code_patch_service.propose_patch(session, issue)


@pytest.mark.asyncio
async def test_propose_patch_api_400_without_model(client, session, tmp_path, monkeypatch):
    monkeypatch.setattr(code_review_service, "_run_ruff", _no_ruff)
    monkeypatch.setattr(code_review_service, "repo_root", lambda: tmp_path)
    src = tmp_path / "apps" / "backend" / "app"
    src.mkdir(parents=True)
    (src / "s.py").write_text("x = 1  # FIXME: y\n", encoding="utf-8")
    await code_review_service.run_self_review(session, tmp_path)
    from app.services import maintenance_service

    issues = await maintenance_service.list_issues(session)
    resp = await client.post(f"/api/v1/maintenance/issues/{issues[0].id}/propose-patch")
    assert resp.status_code == 400
