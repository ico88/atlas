# Resource Telemetry (ROADMAP PR 12)

Live node metrics and Ollama performance, with a bounded history. Node health is
ingested from heartbeats (no new load on the hot path); Ollama latency is
aggregated from the assistant messages the chat layer already records.

## What is collected

- **Node samples** — on each heartbeat the agent's `health` payload
  (`load1`, `ram_free_mb`, and any extra fields) is stored as a `node_metrics`
  row. History is capped per node (`ATLAS_METRICS_HISTORY_LIMIT`, default 500) —
  older samples are pruned on ingest.
- **Ollama performance** — per `(provider, model)`: call count and avg / min / max
  latency, computed from `messages.latency_ms`.

## API

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/v1/metrics/nodes` | Latest sample per node |
| `GET` | `/api/v1/metrics/nodes/{node_id}` | Sample history (`?limit=`, newest first) |
| `GET` | `/api/v1/metrics/ollama` | Latency aggregated per provider/model |

## UI

The **Resources** page (sidebar → Resources) shows per-node load / free RAM cards
and an Ollama latency table, refreshed every few seconds.

## Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `ATLAS_METRICS_HISTORY_LIMIT` | `500` | Samples kept per node before pruning (0 = unbounded) |

## Notes

- Ingestion is best-effort: a telemetry failure never breaks a heartbeat.
- No agent changes are required — the existing heartbeat `health` payload is the
  source; richer fields (CPU %, GPU util, disk) flow through automatically once
  the agent reports them.
