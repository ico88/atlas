# Changelog

All notable changes to ATLAS are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
[Semantic Versioning](https://semver.org/).

## [0.1.0] — 2026-09-16

First public release under the Apache License 2.0. ATLAS is a **local-first,
distributed, multi-agent, human-governed** AI platform you run on your own
hardware.

### Chat & inference
- Streaming chat with file upload, slash commands, web-search grounding with
  citations, per-message 👍/👎 feedback, and a mobile-friendly composer.
- Multi-runtime model gateway: Ollama, OpenAI-compatible (llama.cpp / vLLM /
  LocalAI / OpenAI), Anthropic, and an echo stub — with circuit breaker,
  capacity reservation, benchmarking and health-based fallback.

### Distributed fleet
- Control plane plus worker **nodes** joining over an encrypted ZeroTier
  overlay, enrolling with mTLS and advertising capabilities.
- Resilient scheduler (lease, checkpoint, fencing, failover); capability-based
  remote execution; one-click model pull with progress; fleet deployments,
  versioning and quarantine.
- Isolated workspace **environments** with snapshot/restore.

### Knowledge & memory
- Document RAG and a memory lifecycle (capture, retrieval, provenance,
  retention).

### Self-improvement (Autopilot) — propose-only
- Autonomous proposer for model changes **and** the platform's own code.
- A/B experiments on eval suites; canary rollout with a health gate and
  automatic rollback.
- Code self-review (ruff, TODO/FIXME markers, oversized files) → real,
  sandbox-validated **code patches** written by a code-capable local model.
- Local **LoRA fine-tuning** from thumbs-up interactions; the quality signal
  feeds adaptive routing.
- A single **Autopilot** panel to see and act on everything the system does on
  its own. Applying, merging or swapping the default always waits for a human.

### Governance & security
- RBAC, JWT auth, TOTP MFA, an encrypted-at-rest secret manager, an internal
  PKI issuing node certificates, service accounts, a tamper-evident (hash-chain)
  audit log, SLOs/alerts, and a CycloneDX SBOM.

### Operations
- Role-aware installer and in-app guided setup wizards; transactional updater
  (`./atlas update`) with snapshot and rollback; self-healing maintenance behind
  an approval gate.
- Internationalization (English/Italian).

### Engineering
- FastAPI + async SQLAlchemy + Alembic + Redis backend; Next.js 14 + TypeScript
  frontend; async Python node agent; Caddy; Docker Compose.
- Hermetic test suites (SQLite + fakeredis, no network or GPU), `ruff` + `mypy`,
  and CI running lint, typecheck, tests, Docker build and secret scanning.

### Honesty by construction
- A capability that needs hardware or a model it doesn't have fails clearly
  instead of faking a result. ATLAS makes the best use of the models you give
  it; it does not synthesize a more capable base model on its own.

[0.1.0]: https://github.com/ico88/atlas/releases/tag/v0.1.0
