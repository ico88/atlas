"""Unit tests for the Maintenance Agent git guardrails (spec §11.2)."""

from __future__ import annotations

import pytest
from app.maintenance.git import (
    AuditGitProvider,
    GitGuardrailError,
    GitHubGitProvider,
    check_action,
    get_provider,
)


def test_forbidden_actions_rejected():
    for action in ("push_main", "merge", "force_push", "delete_repository"):
        with pytest.raises(GitGuardrailError):
            check_action(action)


def test_cannot_touch_protected_branches():
    with pytest.raises(GitGuardrailError):
        check_action("push", branch="main")
    with pytest.raises(GitGuardrailError):
        check_action("create_branch", branch="master")


def test_audit_provider_allows_feature_branch_flow():
    provider = AuditGitProvider()
    provider.create_branch("maintenance/abc123")
    provider.commit("maintenance/abc123", "fix: something")
    provider.push("maintenance/abc123")
    url = provider.open_pr("maintenance/abc123", base="main", title="fix")
    actions = [r.action for r in provider.records]
    assert actions == ["create_branch", "commit", "push", "open_pr"]
    assert all(r.allowed for r in provider.records)
    assert url.startswith("dry-run://")


def test_audit_provider_refuses_push_to_main():
    provider = AuditGitProvider()
    with pytest.raises(GitGuardrailError):
        provider.push("main")


def test_default_provider_is_dry_run():
    # With GitHub off (the default) the real repo is never touched.
    assert isinstance(get_provider(), AuditGitProvider)
    assert not isinstance(get_provider(), GitHubGitProvider)


def test_github_provider_requires_credentials():
    with pytest.raises(GitGuardrailError):
        GitHubGitProvider(token="", repo="", api="https://api.github.com")


def test_github_provider_keeps_guardrails():
    provider = GitHubGitProvider(
        token="t", repo="owner/repo", api="https://api.github.com"
    )
    # Even the real provider can never push to a protected branch.
    with pytest.raises(GitGuardrailError):
        provider.push("main")
