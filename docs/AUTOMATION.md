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

## Autonomous proposer (no human input)

ATLAS can also **generate the proposals itself**: a background sweep proposes
adopting each available model (that isn't the current default and has no open
proposal) as the default, on the newest eval suite. Each created proposal
auto-experiments, so the whole chain — propose → experiment → verdict → approval
gate — runs with **zero human input up to the approval**. Only the final apply
(changing the default model) stays human-gated.

- Timer loop: started at boot when `ATLAS_IMPROVEMENT_AUTO_PROPOSE_ENABLED` is on
  (default), every `ATLAS_IMPROVEMENT_AUTO_PROPOSE_INTERVAL` seconds. It is a
  no-op until there is an eval suite and at least one alternative model, so it is
  safe to leave running.
- On demand: `POST /api/v1/improvements/auto-propose`, or the **Generate proposals
  now** button on the Improvements page.
- Idempotent: never creates a duplicate proposal for a candidate that already has
  an open (DRAFT/EXPERIMENTED/APPROVED) proposal.

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
| `ATLAS_IMPROVEMENT_AUTO_PROPOSE_ENABLED` | `true` | timer sweep that generates proposals autonomously |
| `ATLAS_IMPROVEMENT_AUTO_PROPOSE_INTERVAL` | `3600` | seconds between autonomous proposer sweeps |

Set either to `false` to return that loop to fully manual.
