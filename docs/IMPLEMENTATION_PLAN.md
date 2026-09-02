# Implementation Plan

Milestone roadmap derived from the ATLAS/ALMA specification (§16). The platform
is built incrementally; each milestone keeps the application runnable and tested.

| Milestone | Output | Status |
|-----------|--------|--------|
| **M0 — Repository bootstrap** | Repo, branch protection, README, SECURITY, issue templates, minimal CI, `.env.example` | ✅ done (Sprint 1) |
| **M1 — Foundation** | Docker Compose, Postgres, Redis, FastAPI, Next.js, healthcheck, structured logging, auth | ✅ done (incl. JWT auth: login / me / bcrypt) |
| **M2 — Local AI** | Ollama, hardware scan, Model Registry, local streaming chat, history | ✅ done (Ollama provider + echo fallback, AI Router, SSE chat, conversations, model registry, hardware scan) |
| **M3 — Task Engine** | Persistent tasks, queue, concurrency limits, base scheduler, event stream | ✅ done (concurrency limits, retry+backoff, delayed-queue scheduler, DAG dependencies, idempotency) |
| **M4 — Node Federation** | Node Agent, register/heartbeat, capability discovery, remote execution | ✅ done (register/heartbeat + liveness, capability-based scheduling, atomic claim, remote execution with result reporting + retry) |
| **M5 — ALMA** | Task decomposition, DAG, parallel subtasks, retry, result aggregation | ✅ done (objective → DAG decomposition, parallel subtasks, retry, aggregation, failure propagation) |
| **M6 — Maintenance Core** | Log fingerprint, issue, branch, patch, tests, PR, approval gate | ✅ done (fingerprint→issue dedup, analyze, guard-railed branch/patch/tests/PR dry-run, git_actions audit, human approval gate) |
| **M7 — Manual Escalation** | ChatGPT/Claude package prep + import + validation | ✅ done (package builder §10, prepare-from-issue, untrusted response import, human validate/reject; no browser automation) |
| **M8 — RAG/Memory** | Documents, pgvector, retrieval, citations, memory | ✅ done (ingest+chunk+embed, cosine retrieval with citations, semantic memory, feedback; local/Ollama embedders. pgvector = future optimization) |
| **M9 — Optional Cloud** | LiteLLM, OpenAI/Anthropic APIs, budget & fallback | ⬜ planned |
| **M10 — Optimization** | Router learning, cost/latency optimizer, evaluation dataset | ⬜ planned |

**M0–M8 are complete.** M9 (optional cloud) and M10 (optimization) are folded
into the forward plan below rather than pursued standalone.

## Continuation: releases R1–R7

The spec's milestones bootstrapped the platform. The **forward plan** — hardening
the milestones into a distributed, governed, self-improving product — is tracked
in [ROADMAP.md](ROADMAP.md) as releases **R1–R7** and **PR 1–26**. Each release
builds on the milestones already delivered:

| Release | Focus | Builds on / relates to |
|---------|-------|------------------------|
| **R1 — Local Reliable** | Ollama lifecycle automation, multi-vendor GPU discovery, model update/rollback, local resource dashboard, transactional updater, backup/restore | Extends **M2** (Local AI) + M2 hardware scan |
| **R2 — Distributed** | Node Setup UI, ZeroTier, UI enrollment + mTLS, resilient scheduler (lease/fencing/checkpoint), fleet rolling update, compliance/auto-heal | Extends **M4** (Node Federation) |
| **R3 — Workspace** | Environments + manifest, controllable memory, conversation queue, interruptible/background queries, artifact store, snapshots | Extends **M3** (Task Engine) + **M5** (ALMA) + **M8** (memory) |
| **R4 — Connected** | Controlled web search/fetch (SSRF-safe), ranking, citations, cache/budget, web capability on nodes | New; consumes **M8** (RAG) + **M4** capabilities |
| **R5 — Governed** | RBAC/MFA, secret manager + PKI, append-only audit, evals + baselines, multi-model critical review, SLOs, supply-chain | Extends **M1** (auth) + **M6** governance |
| **R6 — Adaptive** | Real self-healing (sandbox, real GitHub PRs), Continuous Improvement, A/B, canary + health gate + rollback | Extends **M6** (Maintenance Core, currently dry-run) |
| **R7 — Highly Available** | Replicated control plane, HA Postgres/queue, leader election, DR | New (final hardening) |

**M9 → cloud providers** (OpenAI/Anthropic via LiteLLM, budget & fallback) slots
into the provider-agnostic AI Router as an extension delivered alongside **R1/R5**
(routing + governance). **M10 → optimization** (router learning, cost/latency
optimizer, evaluation dataset) is delivered by **R5 evals** + **R6 continuous
improvement**.

## Non-negotiable principles (§2)

Local-first · Distributed-by-design · Concurrent-by-design · Provider-agnostic ·
Human-governed · Observable · Fail-safe · Least privilege.

See [SPRINT1.md](SPRINT1.md) for what Sprint 1 delivered and its acceptance
criteria, and [ROADMAP.md](ROADMAP.md) for the forward plan (R1–R7, PR 1–26).
