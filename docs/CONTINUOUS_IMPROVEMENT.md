# Continuous Improvement (ROADMAP PR 18)

Propose a change, prove it with an experiment, and adopt it **only after a human
approves**. Built on the eval harness (PR 16) and the approval gate (§14) — the
same governance posture as self-healing (PR 17). Nothing is ever applied
automatically.

## Lifecycle

```
proposal (DRAFT)
   → experiment   → run baseline vs candidate on an eval suite
                    → compare metrics → recommendation (improvement/regression/…)
                    → EXPERIMENTED + PENDING approval        ← human gate
   → approve       → APPROVED   (authorizes, does not apply)
   → apply         → APPLIED    (governed: sets the default model, etc.)
```

A proposal carries a `title`, a `category` (`model` / `config` / `prompt`), the
eval `suite_id`, the `baseline_model` and `candidate_model`, and a `change` (what
`apply` will do — for a model proposal this is `{"default_model": <candidate>}`,
filled in automatically).

## Experiment & comparison

`experiment` runs the eval suite twice through the AI router (offline echo
provider in tests) — once for the baseline model, once for the candidate — and
compares their aggregate metrics with a **pure** function:

- Deltas are computed for `pass_rate`, `avg_quality`, `avg_safety`,
  `avg_latency_ms`, `p95_latency_ms` (candidate − baseline).
- Verdict:
  - **regression** — safety dropped (overriding), or quality/pass_rate dropped
    with no offsetting gain;
  - **improvement** — quality/pass_rate gained with no drop;
  - **neutral** — no meaningful change;
  - **inconclusive** — not enough data.

Both eval runs are persisted (baseline flagged), and the proposal records
`baseline_run_id`, `candidate_run_id`, the full `comparison`, and the
`recommendation`.

## Approval & apply

The experiment opens a `PENDING` approval (`subject_type=improvement_proposal`).
Approving sets the proposal to `APPROVED` — it **authorizes** the change but does
not apply it. `apply` is a separate, explicit step that refuses unless the
proposal is `APPROVED` (409 otherwise); for a model proposal it sets the runtime
default model via the settings service, then marks the proposal `APPLIED`. Other
categories record the applied intent; concrete appliers plug in at the same seam.

## API

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/improvements/proposals` | create a proposal |
| `GET`  | `/api/v1/improvements/proposals` | list (filter `?status=`) |
| `GET`  | `/api/v1/improvements/proposals/{id}` | one proposal |
| `POST` | `/api/v1/improvements/proposals/{id}/experiment` | run baseline vs candidate, open approval gate |
| `POST` | `/api/v1/improvements/proposals/{id}/apply` | apply an **approved** proposal (409 if not approved) |

Approvals are decided through the existing `/api/v1/approvals/*` endpoints.

## UI

The **Improvements** page creates a proposal (title + suite + baseline/candidate
model), runs the experiment, shows the verdict and metric deltas, and offers
**Approve / Reject** then **Apply** — the whole governed loop in one place.

## Data model

Migration `0017_improvements` adds `improvement_proposals`. No new configuration.
