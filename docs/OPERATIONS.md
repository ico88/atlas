# Operations (ROADMAP PR 4)

Everyday running of ATLAS: one-command tasks, where the logs and audit trails
live, and how to keep the fleet tidy. Protected model pruning and the transactional
updater are covered in [MODEL_OPERATIONS.md](MODEL_OPERATIONS.md) and
[UPDATER.md](UPDATER.md).

## Make targets

`make help` lists everything. The common ones:

| Target | What it does |
|--------|--------------|
| `make up` / `make dev` | start the stack (prod / dev overrides) |
| `make ai-up` | start including local AI (Ollama, profile `ai`) |
| `make down` / `make logs` / `make status` | stop / tail logs / show services |
| `make update` / `make update-status` | transactional update / last result |
| `make backup` | settings (`.env`) + PostgreSQL dump |
| `make health` | curl the backend `/health` |
| `make model-update MODEL=…` / `model-rollback` / `model-list` | model lifecycle |
| `make model-prune` / `make gpu-status` | tidy models / verify GPU use |
| `make migrate` | apply DB migrations in the backend container |
| `make check` | lint + type-check + tests (CI parity) |

Everything is idempotent and safe to re-run; `make update` never runs `down -v`
and always backs up first.

## Logging

The backend emits **structured JSON logs** (one object per line) via
`app/core/logging.py`, each carrying a `request_id` (and `task_id` when relevant)
so a request can be traced end to end. Level is set by `ATLAS_LOG_LEVEL`
(`INFO` by default; `DEBUG` for detail). Tail them with:

```
make logs                 # everything
./atlas logs backend      # one service
```

Notable event names to grep: `http_request`, `chat_stream_error`,
`deploy_advanced`, `deploy_rolled_back`, `auto_remediate`, `maint_fix_proposed`,
`review_done`, `auto_propose`.

## Audit trails

Human-governed and automated actions are recorded in the database, not just the
logs:

| Table | Records |
|-------|---------|
| `git_actions` | every maintenance Git operation (incl. blocked ones) |
| `remediation_events` | remediate / quarantine / reinstate on nodes |
| `approvals` | every human approval decision (who / when / reason) |
| `task_events` / `query_events` | task and background-query lifecycle |
| `deployments` / `deployment_targets` | fleet rollout waves and outcomes |
| `critical_reviews` | proposer/critic/verifier/judge runs |

## Housekeeping

- **Models**: `make model-prune` frees disk while protecting the active,
  rollback-previous and embedding models.
- **Node metrics**: capped per node by `ATLAS_METRICS_HISTORY_LIMIT`.
- **Memory**: expired non-pinned memories are removed by
  `POST /api/v1/memories/prune`.
- **Backups**: `make backup` writes to `.atlas/backups/<timestamp>/`; keep or
  ship these off-box as your retention policy requires.

## Health & readiness

`GET /health` is the liveness/readiness probe used by Docker and the updater's
health gate. The **System Status** page and the **Dashboard** surface the same
component health (backend, database, Redis) in the UI.
