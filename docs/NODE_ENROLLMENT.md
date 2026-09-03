# Node Enrollment (ROADMAP PR 6)

Per-node credentials with a **human approval gate**, layered on top of the shared
join token. An operator invites a node (minting a one-time secret), the node
presents it to register/heartbeat/claim, and the operator can **approve**,
**reject**, **revoke**, or **rotate** that node's access independently.

**Off by default.** Set `ATLAS_NODE_ENROLLMENT_REQUIRED=true` to enforce it; until
then the shared-join-token flow is unchanged.

## Lifecycle

```
invite ─▶ PENDING ─(approve)─▶ APPROVED ─(revoke)─▶ REVOKED
             │                     ▲
          (reject)                 └── register + heartbeat allowed while PENDING;
             ▼                          claiming work requires APPROVED
          REJECTED
```

- **PENDING** — the node may register and heartbeat (announce itself) but **cannot
  claim work**.
- **APPROVED** — full access.
- **REJECTED / REVOKED** — the token is refused entirely (401/403).

## API

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/enrollments` | Invite a node `{node_id, label?}` → returns the **one-time token** |
| `GET`  | `/api/v1/enrollments` | List enrollments (token prefix only, never the secret) |
| `POST` | `/api/v1/enrollments/{id}/approve` | Approve |
| `POST` | `/api/v1/enrollments/{id}/reject` | Reject |
| `POST` | `/api/v1/enrollments/{id}/revoke` | Revoke a previously approved node |
| `POST` | `/api/v1/enrollments/{id}/rotate` | Mint a fresh token (old one stops working) |

The node sends its token as the `X-Node-Token` header (the same header the shared
join token uses), so `ATLAS_NODE_TOKEN` on the node carries either.

## UI

The **Nodes** page has an *Enrollment* section: invite a node, copy the one-time
token, and approve / reject / revoke / rotate each enrollment. The token is shown
once at mint/rotate time only.

## Security

- Tokens are high-entropy (`secrets.token_urlsafe(32)`) and stored **only as a
  SHA-256 hash**; the plaintext is returned once and never persisted in the clear.
- Only a non-secret 8-char prefix is kept for display.
- Rotation replaces the hash, so a leaked token is revocable without deleting the
  node.

## Relationship to mTLS

This delivers the **identity and authorization** layer (who a node is, and
whether it may act). Transport-level **mutual TLS** is complementary hardening at
the network edge — terminate it at Caddy or run nodes over the ZeroTier overlay
(PR 5) — and binds to the same per-node identity established here. Full mTLS
certificate issuance is tracked as follow-up transport work; the enforceable
approval/rotate/revoke gate lives here and is active today.
