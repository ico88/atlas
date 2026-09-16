# Contributing to ATLAS

Thanks for your interest in improving ATLAS! This project is **local-first,
human-governed, and honest about its limits** — contributions are welcome as long
as they keep those values.

By contributing you agree that your contributions are licensed under the
project's [Apache License 2.0](LICENSE).

## Ways to contribute

- **Report a bug** — open an issue with the *Bug report* template.
- **Request a feature** — open an issue with the *Feature request* template.
- **Improve docs** — the `docs/` folder and this README always need clarity.
- **Send a pull request** — see the workflow below.

## Development setup

ATLAS is a monorepo: a FastAPI backend, a Next.js frontend, and a Python node
agent.

```bash
# Backend — hermetic tests (SQLite + fakeredis, no external services)
cd apps/backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
ruff check app && mypy app

# Frontend
cd apps/frontend
npm ci
npx tsc --noEmit && npx eslint src

# Node agent
cd services/node-agent
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
```

The full stack runs with Docker:

```bash
cp .env.example .env
docker compose up --build     # then open http://localhost/system
```

## Pull request workflow

1. **Fork** the repository and create a branch off the default branch.
2. Make focused changes with clear commit messages.
3. **Every change must be green before you push:**
   - backend: `pytest`, `ruff check`, `mypy`
   - frontend: `tsc --noEmit`, `eslint`
   - node agent: `pytest`
   These are exactly what CI (`.github/workflows/ci.yml`) runs.
4. Add or update tests. The backend suite is **hermetic** (no network, no GPU) —
   keep it that way: mock model calls and external services.
5. Update the docs and `docs/ROADMAP.md` when behavior changes.
6. Open a PR using the template. Describe *what* changed and *why*.

## Code style & principles

- **Honesty over theatre.** A feature that needs hardware/a model it doesn't have
  must fail clearly, never fake a result. (See the fine-tuning and code-patch
  pipelines for the pattern.)
- **Propose-only for anything irreversible.** Applying a change, merging code, or
  swapping the default model stays behind a human approval gate.
- **Guardrails are not optional.** Sandboxes, audit logs, and approval gates are
  load-bearing; don't route around them.
- Match the surrounding code's style; keep functions pure and testable where
  possible; write comments at the density of the file you're editing.

## Security

Please **do not** open public issues for security vulnerabilities. Follow the
process in [SECURITY.md](SECURITY.md) instead.

## Community

Be respectful. This project follows the
[Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md).
