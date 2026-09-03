# Semi-Automatic Loops

Less busywork, same governance. The **analysis** and **experiment** phases of the
self-healing (PR 17) and continuous-improvement (PR 18) loops run by themselves in
the background, so a human is left with only the **approve / apply** decision.
Irreversible steps — opening a PR, changing the default model — are never done
automatically; they stay behind the human approval gate.

## Maintenance (self-healing)

When a **new** issue is ingested (`POST /api/v1/maintenance/logs`), a background
worker analyses it and prepares a fix, validating the patch in the real sandbox,
until the run reaches `NEEDS_APPROVAL`. Fired only for a brand-new issue (never on
every recurrence) and idempotent (never stacks a second fix / gate). You then
**Approve** and **Apply** from the Maintenance page, which auto-refreshes as the
background work progresses.

## Continuous Improvement

When a proposal is created with an eval suite, a background worker runs the
baseline-vs-candidate **experiment** and opens the approval gate, so the proposal
reaches a verdict (`EXPERIMENTED`) on its own. The Improvements page auto-refreshes
until the verdict + gate appear; you then **Approve** and **Apply**.

## How it works

`app/services/automation_service.py` spawns detached `asyncio` tasks that each own
a fresh DB session (independent of any HTTP request) and are best-effort: a
failure is logged and never breaks the request that triggered it. The core
`advance_issue` / `advance_proposal` functions are synchronous-awaitable and
directly unit-tested; the `maybe_advance_*` wrappers fire them in the background
only when the corresponding flag is on.

## Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `ATLAS_MAINTENANCE_AUTO_FIX_ENABLED` | `true` | on ingest, auto-prepare a sandbox-validated fix (awaiting approval) |
| `ATLAS_IMPROVEMENT_AUTO_EXPERIMENT_ENABLED` | `true` | on create, auto-run the experiment (awaiting approval) |

Set either to `false` to return that loop to fully manual.
