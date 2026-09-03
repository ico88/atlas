# Evals (ROADMAP PR 16)

A small, offline-friendly evaluation harness for **quality**, **safety** and
**performance**. A *suite* holds *cases*; a *run* executes the suite against the
active provider/model and records per-case results plus aggregate metrics. Mark a
run as a **baseline** to compare later runs against.

## Model (migration 0016)

- `eval_suites` → `eval_cases` (input + `expected_substrings` + `forbidden_substrings`
  + category) → `eval_runs` (provider/model, status, metrics, `is_baseline`) →
  `eval_results` (per case: output, passed, quality, safety, latency).

## Scoring (pure, testable)

- **quality** = fraction of `expected_substrings` present in the output
  (case-insensitive); if none declared, 1.0 for any non-empty output.
- **safety** = 1.0 unless a `forbidden_substring` appears (then 0.0).
- **passed** = quality is 1.0 **and** safety is 1.0.
- Aggregate: `pass_rate`, `avg_quality`, `avg_safety`, `avg_latency_ms`,
  `p95_latency_ms`.

## API

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/evals/suites` | Create a suite |
| `GET`  | `/api/v1/evals/suites` | List suites |
| `GET`  | `/api/v1/evals/suites/{id}` | Suite + its cases |
| `POST` | `/api/v1/evals/suites/{id}/cases` | Add a case |
| `POST` | `/api/v1/evals/suites/{id}/run` | Run the suite (`{model?, is_baseline?}`) |
| `GET`  | `/api/v1/evals/suites/{id}/runs` | List runs |
| `GET`  | `/api/v1/evals/runs/{id}` | Run detail + per-case results |

## UI

The **Evals** page: create a suite, add cases (input + expected substrings),
Run / Run-as-baseline, and see a table of runs with pass-rate, quality, safety
and latency.

## Notes

- Runs go through the same AI router as chat, so they exercise the real model
  (or the echo provider offline — deterministic for CI).
- Scoring is substring-based today (transparent, offline); an embedding- or
  judge-based scorer can be layered on without changing the schema.
