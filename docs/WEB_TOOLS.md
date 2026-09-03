# Web Tools (ROADMAP PR 15)

Safe, policy-guarded **web search and fetch** for the AI, with lexical ranking
and **citations**. Local-first: the feature is **off by default** and the
platform never reaches the internet unless an operator opts in.

## Enabling

**From the UI (recommended):** open **Settings → Web tools**, flip *Enabled*,
choose the *searxng* provider and set its URL, then Save. Changes are stored
server-side (the `app_settings` table) and take effect immediately — no restart
and no `.env` edit. These runtime overrides take precedence over the environment
defaults below. The API key is write-only (never shown back).

**From the environment (defaults / headless):**

```bash
# .env
ATLAS_WEB_TOOLS_ENABLED=true
ATLAS_WEB_SEARCH_PROVIDER=searxng
ATLAS_WEB_SEARCH_URL=http://searxng:8080/search   # your self-hosted SearXNG
```

Then `./atlas update` (or `docker compose up -d`). With no provider configured
(`none`), `/fetch` still works for explicit URLs while `/search` returns nothing.

Runtime config API: `GET /api/v1/settings/web`, `PUT /api/v1/settings/web`
(partial update; unknown fields ignored; `api_key` accepted but never returned).

## API

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/api/v1/web/policy` | Report the active policy (no secrets) |
| `POST` | `/api/v1/web/search` | `{query, limit?, fetch_bodies?}` → ranked citations |
| `POST` | `/api/v1/web/fetch`  | `{url}` → title + extracted text (policy-guarded) |

`search` returns citations sorted by relevance:

```json
{
  "query": "…", "provider": "searxng", "count": 2,
  "citations": [
    {"title": "…", "url": "https://…", "snippet": "…", "score": 7.13}
  ]
}
```

When web tools are disabled the endpoints return **403**; a blocked URL returns
**400** with the policy reason.

## Security model (SSRF guard)

Every outbound request is validated **before** and **after** DNS resolution:

1. **Scheme** — only `http`/`https` (no `file:`, `ftp:`, `gopher:`, `javascript:`).
2. **Host** — must have one; allow/deny lists apply (suffix match; deny wins).
3. **Literal IPs** — private/loopback/link-local/reserved/multicast are blocked
   (e.g. `169.254.169.254`, `127.0.0.1`, `10.0.0.0/8`, `192.168.0.0/16`).
4. **Resolved IPs** — the host is resolved and each address re-checked, so a
   public name that resolves to a private address (DNS rebinding) is blocked.
5. **Redirects** — resolved manually; every hop is re-validated by policy.
6. **Caps** — a per-request timeout and a hard body-size cap (`max_bytes`), so a
   huge or slow response cannot exhaust resources (the body is truncated).

`ATLAS_WEB_ALLOW_PRIVATE_IPS=true` disables checks (3)–(4) for development only.

## Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `ATLAS_WEB_TOOLS_ENABLED` | `false` | Master switch |
| `ATLAS_WEB_SEARCH_PROVIDER` | `none` | `none` \| `searxng` \| `json` |
| `ATLAS_WEB_SEARCH_URL` | *(empty)* | Search endpoint (operator-trusted) |
| `ATLAS_WEB_MAX_RESULTS` | `5` | Candidates fetched/ranked |
| `ATLAS_WEB_FETCH_TIMEOUT` | `10` | Seconds per request |
| `ATLAS_WEB_FETCH_MAX_BYTES` | `2000000` | Body size cap (bytes) |
| `ATLAS_WEB_ALLOW_PRIVATE_IPS` | `false` | Allow private targets (dev only) |
| `ATLAS_WEB_DOMAIN_ALLOWLIST` | *(empty)* | Comma host suffixes; if set, only these |
| `ATLAS_WEB_DOMAIN_DENYLIST` | *(empty)* | Comma host suffixes; always blocked |

## Chat integration

The chat streamer wires web tools in end-to-end. Send `web: true` on
`POST /api/v1/chat/stream` (the chat page has a **🌐 Web** toggle): the backend
runs a search, prepends the ranked results as a grounding system message so the
model answers from them and cites `[n]`, streams a `citations` SSE event, and
persists the citations on the assistant message (`messages.citations`, migration
0009) so they reappear on reload. If web tools are disabled the event carries an
empty list plus a `note`, and the reply proceeds normally.

To actually get results you must run a provider: start SearXNG with
`docker compose --profile web up -d searxng` and set
`ATLAS_WEB_TOOLS_ENABLED=true` (defaults already point the backend at
`http://searxng:8080/search`).

## Design notes

- Parsers are **pure and offline-testable**: `policy` (SSRF), `extract`
  (HTML→text, drops scripts/styles), `ranking` (BM25), `search._parse_searxng`.
- The search provider only *proposes* URLs; each is still fetched through the
  policy layer, so a malicious result cannot reach an internal address.
- Ranking is deterministic BM25 today; an embedding reranker (reusing the RAG
  embedder) can be layered on without changing callers.
