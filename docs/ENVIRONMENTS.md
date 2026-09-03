# Environments (ROADMAP PR 13)

An **environment** is a named, isolated workspace: a declarative **manifest**
(the models / capabilities / knowledge-bases it expects) plus **variables**,
against which tasks, queries and memories can be **scoped**. Environments can be
**snapshotted** and **restored**.

## Data model (migration 0014)

- `environments` — `slug` (unique, auto from name), `name`, `description`,
  `status` (ACTIVE/ARCHIVED), `manifest` (JSON), `variables` (JSON).
- `environment_snapshots` — a captured copy of `manifest` + `variables` plus a
  `stats` summary (counts of scoped tasks/queries/memories at capture time).
- `tasks`, `queries`, `memories` gain a nullable, indexed `environment_id`.

## Isolation

Create a task/query/memory with `environment_id` to scope it; list endpoints
accept an `environment_id` filter:

```
POST /api/v1/tasks        { "title": "...", "environment_id": "<id>" }
GET  /api/v1/tasks?environment_id=<id>
POST /api/v1/queries      { "prompt": "...", "environment_id": "<id>" }
GET  /api/v1/queries?environment_id=<id>
```

## API

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/environments` | Create `{name, description?, manifest?, variables?}` |
| `GET`  | `/api/v1/environments` | List (`?include_archived=`) |
| `GET`  | `/api/v1/environments/{ref}` | By id or slug |
| `PATCH`| `/api/v1/environments/{ref}` | Update name/desc/manifest/variables/status |
| `POST` | `/api/v1/environments/{ref}/snapshots` | Capture a snapshot |
| `GET`  | `/api/v1/environments/{ref}/snapshots` | List snapshots |
| `POST` | `/api/v1/environments/snapshots/{id}/restore` | Restore config from a snapshot |

## Snapshot / restore

`snapshot` captures the environment's **configuration** (manifest + variables)
and a stats summary. `restore` reinstates that configuration onto the
environment. By design restore is **config-level**: historical run data
(tasks/queries/memories) is left untouched — restoring reinstates *how* the
environment is set up, not *what* ran in it.

## UI

The **Environments** page (sidebar → Environments): create environments, edit the
manifest/variables JSON, snapshot, and restore — with per-snapshot stats.
