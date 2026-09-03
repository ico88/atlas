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

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

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


class GitHubGitProvider(AuditGitProvider):
    """Real GitHub-backed provider (ROADMAP PR 17), off unless the operator opts in.

    It reuses the guard-railed :class:`AuditGitProvider` (so it can *never* push to
    a protected branch, force-push, merge, or perform any forbidden action) and,
    on :meth:`open_pr`, makes a real ``POST /repos/{repo}/pulls`` call. Branch
    preparation (create/commit/push of the feature branch) is expected to be done
    by the node that holds the working checkout; here those steps are recorded as
    audited intents. This provider is only ever selected *after* a human has
    approved the specific fix (see :func:`get_provider` / the maintenance service).
    """

    def __init__(self, *, token: str, repo: str, api: str) -> None:
        super().__init__()
        if not token or not repo:
            raise GitGuardrailError(
                "GitHub provider requires ATLAS_MAINTENANCE_GITHUB_TOKEN and "
                "ATLAS_MAINTENANCE_GITHUB_REPO"
            )
        self._token = token
        self._repo = repo
        self._api = api.rstrip("/")

    def open_pr(self, branch: str, *, base: str = "main", title: str = "") -> str:
        check_action("open_pr", branch=branch, target=base)
        # Imported lazily so the dry-run path never needs httpx.
        import httpx

        url = f"{self._api}/repos/{self._repo}/pulls"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        body = {"title": title or f"fix: {branch}", "head": branch, "base": base}
        try:
            resp = httpx.post(url, json=body, headers=headers, timeout=15.0)
            resp.raise_for_status()
            pr_url = str(resp.json().get("html_url") or "")
        except Exception as exc:  # noqa: BLE001 - surface a governed failure
            logger.warning(
                "github open_pr failed", extra={"event": "maint_github_pr_error"}
            )
            raise GitGuardrailError(f"GitHub PR creation failed: {exc}") from exc
        self._record(
            GitActionRecord("open_pr", branch=branch, target=base, detail=f"github: {pr_url}")
        )
        return pr_url


def get_provider() -> AuditGitProvider:
    """Return the configured git provider: real GitHub if enabled, else dry-run.

    The default is always the dry-run :class:`AuditGitProvider`; a real provider
    is used only when the operator has explicitly enabled it *and* supplied
    credentials. Either way the same guardrails apply.
    """

    from app.core.config import get_settings

    settings = get_settings()
    if settings.maintenance_github_enabled:
        return GitHubGitProvider(
            token=settings.maintenance_github_token,
            repo=settings.maintenance_github_repo,
            api=settings.maintenance_github_api,
        )
    return AuditGitProvider()
