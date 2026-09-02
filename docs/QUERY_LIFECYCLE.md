# Query Lifecycle (ROADMAP PR 10)

A **query** is a persisted, background-executed AI request. Unlike the ephemeral
`POST /chat/stream` turn (which lives only for the length of the HTTP response), a
query is stored in the database, run in the background, can be **cancelled**, and
is **recovered** if the backend restarts mid-run.

## States

```
PENDING ──▶ RUNNING ──▶ COMPLETED
   │           │
   │           ├──▶ FAILED      (provider/exception; partial result kept)
   ▼           ▼
CANCELLED   CANCELLED           (cooperative cancel; partial result kept)
```

`recover_stale` moves an orphaned `RUNNING` (a backend crashed mid-run) back to
`PENDING` and re-schedules it on startup.

## API

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/queries` | Create a query; runs in the background. Returns **202** with the row |
| `GET`  | `/api/v1/queries` | List queries (`?status=`, `?limit=`) |
| `GET`  | `/api/v1/queries/{id}` | Query detail + its event history |
| `POST` | `/api/v1/queries/{id}/cancel` | Request cancellation |

```jsonc
// POST /api/v1/queries
{ "prompt": "summarise the release notes", "mode": "AUTO", "model": null }
// 202 -> { "id": "…", "status": "PENDING", ... }  (poll GET /{id})
```

## Cancellation

Cancellation is **cooperative** and prompt:

- A fast Redis flag (`atlas:query:cancel:<id>`) is set by `cancel`, and the
  durable `cancel_requested` column is set too (source of truth after a restart).
- `run_query` checks the flag **before each token**, so a running query stops
  quickly and its **partial result is saved** (status → `CANCELLED`).
- Cancelling a `PENDING` query terminates it immediately without running.

## Recovery

Every run refreshes `heartbeat_at` while streaming. On startup the lifespan hook
calls `recover_and_resume()`:

- `stale_after_seconds == 0` (startup default): any `RUNNING` row is necessarily
  orphaned → re-queued to `PENDING` and re-scheduled.
- A positive threshold only recovers rows whose heartbeat is older than it (for a
  periodic sweep where live runs must be left alone).

Recovery re-executes from the start (a token stream cannot be resumed
mid-flight); the audit trail records a `recovered` event.

## Audit

Every transition writes a `query_events` row (`created`, `started`, `completed`,
`failed`, `cancel_requested`, `cancelled`, `recovered`), exposed under the query
detail endpoint — the history survives a restart.
