# Memory Lifecycle (ROADMAP PR 14)

Durable, semantic memories with **provenance**, usage-aware **retrieval**, and
**retention** — built on the existing memory store (migration 0015 extends
`memories`).

## Capture (provenance)

`POST /api/v1/memories` accepts, besides `content`/`scope`/`scope_id`:

| Field | Meaning |
|-------|---------|
| `source` / `source_id` | where it came from (`chat`, `manual`, `task`, …) and its ref |
| `mem_type` | `fact` (default), `preference`, `summary`, … |
| `tags` | free-form labels |
| `importance` | 0–100, used as a retrieval tie-break and retention hint |
| `pinned` | never auto-expires |
| `ttl_seconds` | retention window (0 / omitted → default `ATLAS_MEMORY_DEFAULT_TTL_SECONDS`) |
| `environment_id` | workspace scoping (PR 13) |

## Retrieval

`POST /api/v1/memories/search` returns the top matches by cosine similarity,
tie-broken by `importance`, **excluding expired** memories. Each returned memory
records usage (`access_count++`, `last_accessed_at`), and the hit carries its
provenance (`source`, `mem_type`, `tags`, `importance`, `pinned`).

`GET /api/v1/memories` lists memories (filters: `scope`, `scope_id`,
`environment_id`, `source`, `include_expired`), ordered by importance then
recency.

## Retention

- A memory with a TTL gets an `expires_at`; expired, **non-pinned** memories are
  hidden from list/search and removed by `POST /api/v1/memories/prune`.
- **Pinned** memories ignore TTL and survive pruning; pinning clears any expiry.

## Controls

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/memories/{id}/pin` | `{pinned}` — pin/unpin (unexpirable) |
| `POST` | `/api/v1/memories/{id}/importance` | `{importance}` — set 0–100 |
| `POST` | `/api/v1/memories/prune` | delete expired, non-pinned memories |

## UI

The **Knowledge** page gains a *Memory* section: remember a fact (with source and
pin), recall memories (showing provenance/score), and prune expired ones.

## Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `ATLAS_MEMORY_DEFAULT_TTL_SECONDS` | `0` | Default TTL for new memories (0 = never expire) |
