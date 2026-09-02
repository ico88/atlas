"""Guard-railed Git operations for the Maintenance Agent (spec §11.1, §11.2).

The agent may read, create non-protected branches, commit/push to its own
branch, open/update/comment PRs, and read CI. It must NEVER push to or merge
``main``, force-push, disable branch protection, touch secrets, change
permissions, delete the repo, or deploy without a gate.

This module enforces those rules regardless of the concrete backend. The default
:class:`AuditGitProvider` is a *dry-run*: it records the intended action (for the
``git_actions`` audit trail, §12) and returns synthetic identifiers, so no real
repository is ever mutated automatically. A real GitHub-backed provider can be
plugged in later behind the same interface — the guardrails below still apply.
"""

from __future__ import annotations

from dataclasses import dataclass

PROTECTED_BRANCHES = {"main", "master", "release", "production"}

# Actions the agent is never allowed to perform (spec §11.2).
FORBIDDEN_ACTIONS = {
    "push_main",
    "merge",
    "merge_main",
    "force_push",
    "disable_branch_protection",
    "read_secrets",
    "write_secrets",
    "change_permissions",
    "delete_repository",
    "deploy_production",
}


class GitGuardrailError(RuntimeError):
    """Raised when a requested Git action violates the maintenance policy."""


@dataclass
class GitActionRecord:
    action: str
    branch: str | None = None
    target: str | None = None
    allowed: bool = True
    detail: str | None = None


def check_action(action: str, *, branch: str | None = None, target: str | None = None) -> None:
    """Raise :class:`GitGuardrailError` if the action is not permitted."""

    if action in FORBIDDEN_ACTIONS:
        raise GitGuardrailError(f"Forbidden git action: {action}")
    if action in {"create_branch", "commit", "push"} and branch in PROTECTED_BRANCHES:
        raise GitGuardrailError(f"Refusing '{action}' on protected branch '{branch}'")
    if action == "open_pr" and target in PROTECTED_BRANCHES:
        # Opening a PR *targeting* main is fine (a human merges it); pushing to it is not.
        return


class AuditGitProvider:
    """Dry-run provider: enforces guardrails and records intended actions."""

    def __init__(self) -> None:
        self.records: list[GitActionRecord] = []

    def _record(self, rec: GitActionRecord) -> GitActionRecord:
        self.records.append(rec)
        return rec

    def create_branch(self, branch: str, *, base: str = "main") -> GitActionRecord:
        check_action("create_branch", branch=branch)
        return self._record(
            GitActionRecord("create_branch", branch=branch, target=base, detail="dry-run")
        )

    def commit(self, branch: str, message: str) -> GitActionRecord:
        check_action("commit", branch=branch)
        return self._record(
            GitActionRecord("commit", branch=branch, detail=f"dry-run: {message}")
        )

    def push(self, branch: str) -> GitActionRecord:
        check_action("push", branch=branch)
        return self._record(GitActionRecord("push", branch=branch, detail="dry-run"))

    def open_pr(self, branch: str, *, base: str = "main", title: str = "") -> str:
        check_action("open_pr", branch=branch, target=base)
        self._record(
            GitActionRecord("open_pr", branch=branch, target=base, detail=f"dry-run: {title}")
        )
        # Synthetic URL; a real provider would return the created PR URL.
        return f"dry-run://pull-request/{branch}"
