# Quality: fault injection, failover, recovery & CI (ROADMAP PR 26)

ATLAS is meant to keep running when parts of it fail. This document describes how
that resilience is **verified automatically** — not asserted in prose — plus the
CI gates every change passes and how the AMD GPU path is proven real.

## Fault-injection & recovery suite

`apps/backend/tests/integration/test_resilience.py` injects realistic failures and
asserts the system recovers on its own. It is hermetic (file-backed SQLite + fake
Redis, no sleeps, no external services), so it runs in CI on every push.

| Injected fault | Expected recovery | Mechanism |
|----------------|-------------------|-----------|
| Local worker crashes mid-task | Task reclaimed and re-enqueued (`RETRYING`); the dead owner's lease token is rotated so its late writes are **fenced out** | `scheduler_service.reclaim_expired` + lease fencing (PR 8) |
| Worker crashes repeatedly | Retries are consumed, then the task goes `FAILED` — never an infinite loop | retry accounting in `reclaim_expired` |
| Remote node dies | Task returns to the `QUEUED` claim pool, detached from the dead node, for another node to claim | remote branch of `reclaim_expired` |
| Backend dies mid-chat | Orphaned assistant replies stuck at `pending` are marked `error` on startup (partial text kept), so the UI never shows "working" forever | `chat_service.recover_pending_replies` (called from lifespan) |
| HA leader dies | A standby acquires the Redis lease within `ATLAS_HA_LEASE_TTL` and becomes leader; the recovered node stays a standby — **automatic failover** | `leadership_service` lease election (PR 9) |

The individual primitives also have focused tests: `test_scheduler.py` (lease,
renew, checkpoint, fencing, late tasks), `test_cluster_ha.py` (election, cluster
status), `test_chat.py` (async turn + resume). This suite is the *integration*
layer that exercises them as failure scenarios.

## AMD acceleration — proven, not stubbed

The AMD GPU path (spec §9 / PR 2) is real code with a real device mapping, verified
in `apps/backend/tests/unit/test_shell_scripts.py`:

- `generate_gpu_override <root> vulkan` writes a working Ollama override that passes
  `/dev/dri` through and sets `OLLAMA_VULKAN=1`;
- `generate_gpu_override <root> rocm` maps `/dev/kfd` when the host exposes it;
- `gpu_backend_configured <root>` reads the generated override back to the same
  backend (`vulkan` / `rocm` / `nvidia` / `cpu`).

On a real AMD host, `./atlas gpu-status` reports detected vs. configured backend
and whether Ollama is actually running a model on the GPU — the operator-facing
proof. (The maintainer's Radeon R9 270X is GCN 1.0 and predates ROCm/Vulkan compute
for Ollama, so it runs CPU-only; the Vulkan path targets supported AMD GPUs.)

## CI gates

`.github/workflows/ci.yml` runs on every push and pull request:

- **Backend** — `ruff check`, `mypy`, hermetic `pytest` (the full suite incl. the
  resilience and shell tests above);
- **Backend / PostgreSQL** — `alembic upgrade head` against a real Postgres 16
  service (catches SQLite-only migrations);
- **Node agent** — `ruff` + `pytest`;
- **Frontend** — typecheck, lint, `next build`;
- **Docker build** — builds the backend, frontend and node-agent images and
  smoke-imports `app.main` (catches missing runtime deps);
- **Shell** — `shellcheck -x` on the `atlas` CLI, the installer and every
  `infrastructure/scripts/lib/*.sh`;
- **Secret scan** — Gitleaks over the full history.

## Honest scope

The failure tests cover the coordination logic ATLAS owns. True HA still requires a
highly-available Redis/Postgres underneath (see [HA.md](HA.md)); the election and
reclaim logic here is the coordination primitive on top of it. Node self-update
depends on the agent honoring `desired_version` (see fleet docs).
