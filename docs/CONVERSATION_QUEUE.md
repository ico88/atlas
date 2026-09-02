# Conversation Queue (ROADMAP PR 11)

Back-pressure for per-conversation messages: **immediate send** when idle,
**queueing** when busy, **merge** of rapid consecutive messages, and bounded
**parallelism** across conversations. State lives in Redis, so it is shared
across worker processes and survives a restart.

## Model

- Each **conversation** processes **one turn at a time** (a per-conversation lock).
- Up to `ATLAS_CONVERSATION_MAX_PARALLEL` **different** conversations run at once
  (`0` = unlimited).
- A message to an idle conversation with a free global slot is **dispatched**
  immediately; otherwise it is **queued** (FIFO).
- On `enqueue`, if the tail pending message and the new one are both `user`
  turns, they are **merged** (`merged_count` records how many) — so a burst of
  messages arriving while a turn runs becomes a single next turn.

## API

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/conversations/{id}/messages` | Enqueue `{content, role?, merge?}` |
| `GET`  | `/api/v1/conversations/{id}/queue` | Queue status (active, pending, items) |
| `POST` | `/api/v1/conversations/{id}/queue/complete` | Finish the active turn, dispatch next |

```jsonc
// POST .../messages  -> dispatched (conversation was idle)
{ "status": "dispatched", "conversation_id": "c1", "pending": 0,
  "message": { "id": "…", "role": "user", "content": "hi", "ts": 1.0 } }

// POST .../messages  -> queued (conversation busy)
{ "status": "queued", "conversation_id": "c1", "position": 1, "pending": 1 }
```

## Lifecycle

1. `enqueue` returns **dispatched** with the `message` to run, or **queued**.
2. The caller runs the turn (e.g. via the chat streamer / query lifecycle).
3. When the turn ends, call **complete** — it releases the lock, frees the global
   slot, and returns the **next** message to run (or `null` when the queue drains).

`dispatch_next` re-tries a queued conversation once a global slot frees up;
`clear` drops all pending messages and releases the conversation.

## Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `ATLAS_CONVERSATION_MAX_PARALLEL` | `4` | Max conversations running in parallel (`0` = unlimited) |

## UI

The **Queue** page (sidebar → Queue) drives this API: enter a conversation id,
enqueue messages, watch them dispatch/queue/merge live (polled every 2s), and
press **Complete turn** to release the active turn and dispatch the next.

## Notes

- Kept separate from `POST /chat/stream` (the live SSE streamer) so callers can
  manage back-pressure explicitly; the streamer/query runner calls `complete`
  when a turn finishes to release the conversation.
- Operations are pragmatically atomic (no Lua), matching
  `services/concurrency.py` — acceptable for sprint-scope scheduling and
  compatible with the in-memory Redis fake used by tests.
