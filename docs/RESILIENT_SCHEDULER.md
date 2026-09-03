# Resilient Scheduler (ROADMAP PR 8)

Crash-tolerance for the task engine, layered on the existing queue/retry/DAG
logic. A running task now holds a **lease**; if its worker or node dies, the
scheduler **reclaims** the task and re-runs it, while **fencing** stops the dead
owner from corrupting state.

## Mechanism

- **Lease + fencing token.** When a task goes RUNNING (local worker or node
  claim) it gets a lease (`lease_expires_at`) and a random `lease_token`. Any
  privileged update must present the current token.
- **Heartbeat / checkpoint.** The executor calls `renew_lease` to extend the
  deadline and may pass a `checkpoint` (persisted on the task) so long work can
  resume from the last step instead of restarting.
- **Reclaim (failover).** `reclaim_expired` scans RUNNING tasks whose lease
  passed its deadline and:
  - rotates `lease_token` (so the old owner is fenced out);
  - **local** tasks → `RETRYING`, re-enqueued, `retries` bumped;
  - **remote** tasks → back to the `QUEUED` claim pool (`assigned_node_id`
    cleared);
  - tasks with no retries left → `FAILED`.
  The worker loop runs this sweep every iteration.
- **Late tasks.** After a reclaim the task is no longer RUNNING, so a late result
  from the zombie owner is rejected (`POST /tasks/{id}/result` → 409) and a stale
  `renew_lease`/`save_checkpoint` returns `False`.

## Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `ATLAS_TASK_LEASE_SECONDS` | `60` | Lease duration granted on RUNNING |
| `ATLAS_SCHEDULER_RECLAIM_ENABLED` | `true` | Master switch for the reclaim sweep |

## Data model (migration 0012)

`tasks` gains `lease_token`, `lease_expires_at` (indexed), `heartbeat_at`, and
`checkpoint` (JSON). All nullable and backward-compatible.

## Notes

- Timestamp comparisons tolerate naive datetimes (SQLite test DB).
- The reclaim sweep is idempotent and safe to run from multiple workers: each
  reclaim is a guarded status transition, and the rotated token prevents
  double-processing by the previous owner.
