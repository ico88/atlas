# Security Policy

ATLAS is a **local-first, human-governed** platform. Security is a first-class,
non-negotiable design principle (spec §2, §13).

## Core rules

- **No secrets in Git.** Secrets live only in the environment or a secret store.
  `.env` is git-ignored; only `.env.example` (with placeholders) is committed.
- **Least privilege.** Services and agents receive only the permissions they
  need. Containers run as non-root users.
- **Only HTTPS is exposed.** The reverse proxy (Caddy) is the sole public entry
  point. PostgreSQL, Redis and internal services are never published to the
  public internet.
- **Human governance.** Destructive operations and production deploys require
  explicit approval. The Maintenance Agent (future milestone) may open a Pull
  Request but must never merge to `main`, force-push, or alter branch
  protection.
- **Auditability.** Every task, LLM call, error, retry, escalation and Git
  action must be traceable via the shared correlation id. Secrets, API keys,
  passwords and tokens must never be logged.

## Branch protection expectations

- `main` is protected; changes land via Pull Request with passing CI.
- No direct pushes or force-pushes to `main`.

## Reporting a vulnerability

If you discover a security issue, please open a **private** security advisory or
contact the maintainers directly. Do not disclose details publicly until a fix
is available. Please include:

- A description of the issue and its impact.
- Steps to reproduce.
- Any relevant logs (with secrets redacted).

## Dependencies & scanning

CI runs a secret scan and dependency checks on every pull request. Keep
dependencies pinned and update them promptly when advisories are published.
