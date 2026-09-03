# Self-Healing (ROADMAP PR 17)

Turns the Maintenance Agent's "propose a fix" loop from a **placeholder** into a
**real, governed** one: a proposed patch is validated in an isolated sandbox
(actual patch application + actual check command), and only after a human
approves does the agent open the PR — never touching `main`, never merging.

Builds on M6 (`maintenance_issues` / `maintenance_runs` / `git_actions`,
fingerprinting, the dry-run guard-railed Git provider and the approval gate). No
schema change — the existing run fields (`branch`, `patch`, `tests_summary`,
`pr_url`, `risk`, `status`) already carry everything PR 17 records.

## The loop

```
log → issue (fingerprint, dedup)
      → analyze            (ANALYZED)
      → create-fix         → build patch → REAL sandbox validation
                             → dry-run PR preview (no mutation, audited)
                             → NEEDS_APPROVAL  + PENDING approval  ← human gate
      → approve            (run APPROVED, issue RESOLVED)
      → apply-fix          → open the PR via the configured provider (PR_OPENED)
```

Every step is recorded in `git_actions` (§12), including a `sandbox` row with the
real validation summary and a `blocked` row if a guardrail ever refuses an action.

## Real sandbox

`app/maintenance/sandbox.py` runs a proposed fix for real, safely:

1. A fresh temp directory is created and seeded with the affected file(s).
2. The unified-diff **patch is applied for real** with `git apply` — in *check*
   mode first, so a patch that does not apply cleanly is reported (`applied:
   false`), never force-applied.
3. An operator-configured **check command** runs against the patched tree, and
   its real exit code / output is captured. Empty command ⇒ *apply-only* check
   (the patch must apply cleanly) — still a genuine result.
4. The temp directory is always removed.

Safety by construction:

- The **real repository is never touched** — a bad patch can only break the
  throwaway sandbox.
- The check command comes **only from server config**
  (`ATLAS_MAINTENANCE_CHECK_COMMAND`), never from an API request, so the sandbox
  is not a remote-code-execution surface. Seed paths are contained under the temp
  root (path traversal is rejected). Output is capped; the command has a timeout.

> Honest scope: the agent does not yet *synthesize* a repo-grounded patch from a
> model — that source (an LLM, or the ChatGPT/Claude escalation round-trip) plugs
> in at `_proposed_patch`. What is already real is the **validation** and the
> **governance**: a well-formed patch is actually applied and checked, and the
> recorded result reflects a real execution.

## Governed apply (`apply-fix`)

`apply-fix` is the **only** step that may mutate a real repository. It refuses
unless the run is `APPROVED` (409 otherwise), then replays the git actions
through the configured provider. Guardrails are identical to the dry-run path:
never a protected branch, never `merge`/`force_push`, PR always *targets* `main`
for a human to merge.

## Git provider

`get_provider()` returns the **dry-run** `AuditGitProvider` by default. When the
operator opts in (`ATLAS_MAINTENANCE_GITHUB_ENABLED=true` + token + repo), it
returns `GitHubGitProvider`, which opens a **real** PR via the GitHub REST API —
subject to the same guardrails. Off by default: the loop stays dry-run and never
mutates a real repository until an operator opts in *and* a human approves the
specific fix.

## API

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/maintenance/issues/{id}/create-fix` | build patch, sandbox-validate, open approval gate |
| `POST` | `/api/v1/maintenance/issues/{id}/apply-fix` | open the PR for an **approved** fix (409 if not approved) |
| `POST` | `/api/v1/maintenance/sandbox` | validate an arbitrary `{files, patch}` in the sandbox (command from config only) |

## UI

The **Maintenance** page shows the sandbox result on each run and, once a fix is
approved, an **Apply approved fix (open PR)** button that runs the governed
apply. A run that has been applied shows `PR opened`.

## Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `ATLAS_MAINTENANCE_SANDBOX_ENABLED` | `true` | run the real patch+check sandbox during `create-fix` |
| `ATLAS_MAINTENANCE_SANDBOX_TIMEOUT` | `120` | seconds allowed for the check command |
| `ATLAS_MAINTENANCE_CHECK_COMMAND` | *(empty)* | validation command (apply-only if empty); server-side only |
| `ATLAS_MAINTENANCE_GITHUB_ENABLED` | `false` | use the real GitHub provider for `apply-fix` |
| `ATLAS_MAINTENANCE_GITHUB_TOKEN` | *(empty)* | token for the real provider |
| `ATLAS_MAINTENANCE_GITHUB_REPO` | *(empty)* | `owner/repo` for the opened PR |
