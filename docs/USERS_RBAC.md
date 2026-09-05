# Users & RBAC (ROADMAP PR 27)

Two roles, one switch. Built on the existing auth (User model with `role`, JWT
login, bootstrap admin — spec §15).

## Roles

| Role | Can |
|------|-----|
| `admin` | Everything: manage users, nodes, models, settings, approvals, maintenance, improvements. |
| `user` | Use the app: chat, queries, their own memory/history. |

`admin` always satisfies any role gate.

## Enforcement modes

`ATLAS_AUTH_ENFORCE` decides whether roles are enforced:

- **off** (default) — **local-first, single-operator**: endpoints are open and the
  caller is treated as an admin. A token, if presented, is still honored for
  attribution. This keeps ATLAS usable with zero setup.
- **on** — **multi-user**: management endpoints require a valid **admin** token;
  role gates are enforced. A plain `user` token gets `403` on admin-only routes;
  no/invalid token gets `401`.

### Bootstrap flow

1. Leave enforcement off. Open the **Users** page and create an admin
   (email + password + role `admin`). You can also seed one at startup with
   `ATLAS_ADMIN_EMAIL` / `ATLAS_ADMIN_PASSWORD`.
2. Set `ATLAS_AUTH_ENFORCE=true` and restart. Now login is required; get a token
   from `POST /api/v1/auth/login` and send it as `Authorization: Bearer <token>`.

## Safety

- The service refuses to demote or deactivate the **last active administrator**
  (`409`), so you can never lock yourself out of admin.
- Passwords are hashed (never stored or returned in plaintext); the API never
  returns password hashes.

## API (admin-gated)

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/api/v1/users` | list users (+ `auth_enforced` flag) |
| `POST` | `/api/v1/users` | create a user (`email`, `password`, `role`) |
| `PATCH`| `/api/v1/users/{id}` | change `role` and/or `is_active` |
| `POST` | `/api/v1/auth/login` | exchange credentials for a JWT |
| `GET`  | `/api/v1/auth/me` | the current token's user |

## UI

The **Users** page lists users, creates them, toggles admin/user, and
activates/deactivates — and shows whether enforcement is currently on, with the
open-mode bootstrap hint.

A **/login** page signs in (email + password) and stores the JWT; the token is
attached to every API call automatically. The sidebar shows who is signed in and
a **Log out** button (or a **Log in** link when signed out). In open mode login
is optional (used for per-user scoping / attribution); with enforcement on it is
required for admin-gated actions.

## Dependencies

`app/api/deps.py` exposes `require_admin` / `require_user` (from `require_role`)
and `current_user_optional`; reuse them to gate other routes as multi-user rolls
out. Per-user data scoping and anonymous vs. tracked modes are **PR 28**.
