# Multi-runtime / multi-model architecture (Fase 1)

ATLAS is an **AI orchestration platform**, not a front-end for Ollama. ALMA never
talks to a concrete engine: it asks the **Model Gateway** for a capability (or an
alias) at a privacy level, and the system decides *which model, on which runtime,
on which node* to use.

```
ALMA / chat
   │  "I need CHAT + CODING, LOCAL_ONLY"
   ▼
AI Router  ──►  Model Gateway  ──►  Runtime Adapter
                                     ├── Ollama        (native API)
                                     ├── OpenAI-compat (llama.cpp / LocalAI / vLLM / OpenAI)
                                     └── Anthropic     (Fase 3)
```

## What Fase 1 delivers

- **`RuntimeAdapter`** (`app/ai/base.py`) — the uniform interface every engine
  implements (`is_available`, `health`, `list_models`, `stream_chat`).
  `ChatProvider` is kept as an alias so existing callers are untouched.
- **Adapters**: `OllamaProvider` (existing, now with `health()`), `EchoProvider`
  (fallback), and **`OpenAICompatAdapter`** — one adapter that speaks the OpenAI
  wire format and therefore covers **llama.cpp (`llama-server`), LocalAI, vLLM and
  OpenAI** by pointing `endpoint` at each.
- **Registries** (migration `0022`):
  - `runtimes` — a registered engine instance (type, endpoint, node, limits);
  - `model_deployments` — the join *model × runtime × node*, with priority and a
    place for benchmarked throughput;
  - `model_aliases` — `atlas.general` → ordered list of `model_key`s;
  - `models` gains `model_key`, `quantization`, `format`, `parameter_count`.
- **Model Gateway** (`app/ai/gateway.py`) — builds candidates from the registries,
  filters by **capability** and **privacy**, scores them, and returns the best
  **healthy** one, skipping DOWN runtimes (automatic fallback). Every decision is
  logged for explainability.
- **Router integration** — `router.select()` uses the gateway when any deployment
  is registered; with none, it keeps the classic Ollama-or-echo path, so existing
  installs behave exactly as before (zero regression).
- **API** — `/api/v1/runtimes` (+ `/runtimes-health`), `/api/v1/model-deployments`,
  `/api/v1/model-aliases`.
- **UI** — the **AI Runtimes** page (register runtimes, see live health, manage
  deployments and aliases).

## Routing: capabilities, privacy, scoring

A request carries `required_capabilities` and a `privacy` level:

| Privacy | Cloud runtimes eligible? |
|---|---|
| `LOCAL_ONLY` | never |
| `LOCAL_PREFERRED` | only if `ATLAS_ROUTING_CLOUD_ALLOWED=true` (local scored higher) |
| `CLOUD_ALLOWED` | only if the global flag is on |
| `CLOUD_REQUIRED` | only cloud |

Scoring (`score_candidate`, a pure, unit-tested function):

```
score = 5 × matched-capabilities
      + deployment.priority
      + runtime-type preference (ATLAS_RUNTIME_PRIORITY order)
      + local bonus (when routing_local_first)
      + ½ × benchmarked tokens/s
      + alias order (dominant, when routing via an alias)
      − registration tie-break
```

Node-load and free-VRAM terms are deliberately left as TODOs for **Fase 2** — they
need live telemetry to mean anything, and adding them now would be guesswork.

## Configuration

```
ATLAS_ROUTING_LOCAL_FIRST=true          # prefer local over cloud when both qualify
ATLAS_ROUTING_CLOUD_ALLOWED=false       # global gate for cloud runtimes
ATLAS_RUNTIME_PRIORITY=["llama_cpp","ollama","openai_compat","vllm"]
```

## Honest scope & the road ahead

Fase 1 is the **foundation + local routing**, exactly the sprint in the design
brief (#47/#48). It is real, not a stub: the acceptance test registers two runtimes
on one node, routes a chat request to the winning deployment, and falls back when
that runtime is stopped.

- **Fase 2** ✅ (partial) — **benchmarks** (`benchmark_service`: measured
  tokens/sec + first-token latency, persisted on the deployment and fed into the
  score) and a per-runtime **circuit breaker** (`app/ai/circuit.py`, Redis-backed:
  opens after N consecutive failures, cools down, then probes to recover; the
  gateway skips OPEN runtimes and records health failures). A configurable retry
  budget rounds it out. UI: a Circuit badge and a per-deployment Benchmark button.
  Node-load and VRAM score terms still need live telemetry — deferred to Fase 4.
- **Fase 3** ✅ (**M9**) — the **Anthropic** adapter (Messages API) plus **OpenAI**
  through `OpenAICompatAdapter`; a **`routing_policies`** table (per task type:
  capabilities, preferred alias, privacy, ordered fallback) and
  `gateway.resolve_for_task`, which tries the preferred alias then each fallback —
  the router-level **escalation** chain (e.g. local → OpenAI → Anthropic when the
  policy allows cloud). API `/routing-policies`. Cloud is reached only when a
  runtime is registered for it AND privacy/policy allow (`LOCAL_ONLY` always
  excludes cloud). To enable M9: register an `openai`/`anthropic` runtime with an
  API key, add a deployment + alias, set `ATLAS_ROUTING_CLOUD_ALLOWED=true`, and a
  policy whose fallback points at the cloud alias.
- **Fase 4** — resource reservation, model load/unload strategy, preemption.

Distributing a **single** LLM across nodes over WAN is intentionally out of scope
(a different, harder problem); ATLAS uses distributed *task* execution instead.
