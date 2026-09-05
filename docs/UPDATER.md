# Unified Updater (ROADMAP PR 20)

One command updates the whole stack transactionally and reports a single clear
result — no manual steps left behind.

```
sudo ./atlas update           # full transactional update
sudo ./atlas update --resume  # re-run after an interrupted attempt
./atlas update-status         # show the last update log
```

## What it does, in order

1. **Preflight** (nothing is changed if this fails): Docker reachable, the compose
   configuration is valid, and at least ~2 GB of free disk. Failure → result
   `aborted`.
2. **Snapshot**: records the current git revision (for rollback) and backs up
   `.env` + a PostgreSQL dump to `.atlas/backups/<timestamp>/`.
3. **Apply**: `git pull --ff-only` (your `.env` is git-ignored and never touched),
   then `docker compose up -d --build`. Migrations run via the backend entrypoint.
   Data volumes (`pgdata`, `redisdata`, `ollamadata`) are always preserved — the
   updater never runs `down -v`.
4. **Verify**: waits for the backend `/health` to go green.
5. **Rollback on failure**: if build or health fails, the code is reset to the
   pre-update revision (only if a pull happened) and rebuilt back to a healthy
   state.

## Single result (and exit code)

| Result | Meaning | Exit |
|--------|---------|------|
| `completed` | updated and healthy | 0 |
| `rolled-back` | update failed; previous version restored and healthy | 1 |
| `aborted` | preflight failed; nothing changed | 1 |
| `manual` | could not reach a healthy state either way — see `./atlas logs backend` | 2 |

The result is printed as the final `RESULT:` line, appended to
`.atlas/state/update.log`, and stored in `.atlas/state/last-result`.

## Safety

- A lock (`.atlas/update.lock`) prevents concurrent updates; `--resume` clears a
  stale lock from an interrupted run.
- Settings and memory survive updates: `.env` is git-ignored, data lives in named
  Docker volumes, and a DB dump is taken before every update.
