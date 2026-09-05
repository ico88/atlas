# Critical Review (ROADMAP PR 19)

A multi-role quality pipeline that turns a single prompt into a vetted answer:
**proposer → critic → verifier → judge**, across several rounds, keeping the best
by **adaptive consensus**. The scoring roles are pure functions (offline-testable);
only the proposer touches a model (the echo provider when offline).

## Roles

- **Proposer** — generates a candidate answer via the AI router (a small system
  prompt asks for accuracy/concision; later rounds are told to improve on prior
  attempts).
- **Critic** — heuristic flaws in the candidate: `empty` (severe), `thin` (short),
  `refusal` (deflects), `hedging` (low confidence). Each finding has a severity.
- **Verifier** — checks the answer against caller-supplied **reference facts**:
  `grounding` = fraction of references present; the rest are `unsupported`. With no
  references, grounding is neutral (skipped).
- **Judge** — combines them into a score and a decision:
  `quality = 1 − Σ severity_weights` (severe 1.0, major 0.4, minor 0.2, note 0.1);
  with references, `score = 0.5·quality + 0.5·grounding`. Decision:
  `≥ accept` → **accept**, `≥ revise` → **revise**, else **reject**.

## Adaptive consensus

Up to `ATLAS_REVIEW_MAX_ROUNDS` candidates are produced; the loop **stops early**
the moment a round clears the accept threshold. The best round (highest score)
wins; `agreement` = the fraction of rounds sharing the winning decision.

## API

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/reviews` | run a review (`prompt`, optional `references`, `max_rounds`, `model`) |
| `GET`  | `/api/v1/reviews` | list recent reviews |
| `GET`  | `/api/v1/reviews/{id}` | full review (all rounds, findings, verification, consensus) |

Each run is persisted (`critical_reviews`, migration 0019) for audit.

## UI

The **Critical Review** page takes a prompt and optional reference facts, runs the
pipeline, and shows the decision, best answer, and every round with its findings,
grounding and score.

## Honest scope

The verifier grounds against **provided** references (substring match) — it does
not fact-check the open world. The critic is heuristic. Both get much stronger
with a capable model and richer references; the pipeline and its scoring/consensus
are the durable part, and a model-based critic/verifier can plug in behind the same
roles.

## Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `ATLAS_REVIEW_MAX_ROUNDS` | `3` | candidates before picking the best |
| `ATLAS_REVIEW_ACCEPT_THRESHOLD` | `0.8` | score to accept (and stop early) |
| `ATLAS_REVIEW_REVISE_THRESHOLD` | `0.5` | score to revise (else reject) |
| `ATLAS_REVIEW_MIN_ANSWER_CHARS` | `40` | shorter answers are flagged as thin |
