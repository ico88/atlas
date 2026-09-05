# Anonymous & Per-User Modes (ROADMAP PR 28)

Two privacy behaviours on top of Users & RBAC (PR 27). No migration — reuses
`conversations.user_id` and `memories.scope_id`.

## Anonymous mode (saves nothing)

Send a chat turn with `"anonymous": true`. The reply streams normally, but the
turn persists **nothing**: no conversation, no messages, no memory capture, and
no memory recall — a clean, private turn. The `start`/`done` events carry a null
`conversation_id`, so the client keeps it out of the history list.

In the chat UI it's the **🕶 Incognito** toggle next to 🌐 Web.

## Per-user data (tracked mode)

When a request carries a valid token, the caller's data is scoped to them:

- **Conversations** created in the turn get `user_id = <caller>`.
  `GET /api/v1/conversations` returns only the caller's conversations; an
  **admin** sees everyone's; with **no token** (open, single-operator mode) it
  returns the unowned conversations — the operator's own history.
- **Memory** auto-captured from chat is stored with `scope_id = <caller>` and
  recalled filtered by that scope, so each user's remembered facts
  ("sono Federico") stay their own. With no token, memory is unscoped as before.

This works whether or not `ATLAS_AUTH_ENFORCE` is on: a presented token is always
honoured for scoping. Turning enforcement on additionally *requires* a token on
gated endpoints (see USERS_RBAC.md).

> Scope note: queries (PR 10) are not yet per-user (no `user_id` column); that can
> be added later the same way. Conversations and chat memory are covered here.

## Summary

| Mode | History | Memory | Visibility |
|------|---------|--------|------------|
| Anonymous (`anonymous: true`) | not saved | not saved / not used | — |
| Tracked (token present) | saved, owned by user | saved, scoped to user | user sees own; admin sees all |
| Open (no token) | saved, unowned | saved, unscoped | single-operator |
