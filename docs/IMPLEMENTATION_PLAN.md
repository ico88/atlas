# Implementation Plan

Milestone roadmap derived from the ATLAS/ALMA specification (§16). The platform
is built incrementally; each milestone keeps the application runnable and tested.

| Milestone | Output | Status |
|-----------|--------|--------|
| **M0 — Repository bootstrap** | Repo, branch protection, README, SECURITY, issue templates, minimal CI, `.env.example` | ✅ done (Sprint 1) |
| **M1 — Foundation** | Docker Compose, Postgres, Redis, FastAPI, Next.js, healthcheck, structured logging, auth | ✅ done (incl. JWT auth: login / me / bcrypt) |
| **M2 — Local AI** | Ollama, hardware scan, Model Registry, local streaming chat, history | ✅ done (Ollama provider + echo fallback, AI Router, SSE chat, conversations, model registry, hardware scan) |
| **M3 — Task Engine** | Persistent tasks, queue, concurrency limits, base scheduler, event stream | ✅ done (concurrency limits, retry+backoff, delayed-queue scheduler, DAG dependencies, idempotency) |
| **M4 — Node Federation** | Node Agent, register/heartbeat, capability discovery, remote execution | 🟡 minimal (register/heartbeat + node agent + liveness done; scheduling & remote exec pending) |
| **M5 — ALMA** | Task decomposition, DAG, parallel subtasks, retry, result aggregation | ✅ done (objective → DAG decomposition, parallel subtasks, retry, aggregation, failure propagation) |
| **M6 — Maintenance Core** | Log fingerprint, issue, branch, patch, tests, PR, approval gate | ✅ done (fingerprint→issue dedup, analyze, guard-railed branch/patch/tests/PR dry-run, git_actions audit, human approval gate) |
| **M7 — Manual Escalation** | ChatGPT/Claude package prep + import + validation | ⬜ planned |
| **M8 — RAG/Memory** | Documents, pgvector, retrieval, citations, memory | ⬜ planned |
| **M9 — Optional Cloud** | LiteLLM, OpenAI/Anthropic APIs, budget & fallback | ⬜ planned |
| **M10 — Optimization** | Router learning, cost/latency optimizer, evaluation dataset | ⬜ planned |

## Non-negotiable principles (§2)

Local-first · Distributed-by-design · Concurrent-by-design · Provider-agnostic ·
Human-governed · Observable · Fail-safe · Least privilege.

See [SPRINT1.md](SPRINT1.md) for what Sprint 1 delivered and its acceptance
criteria.
